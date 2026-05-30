"""MinerU 云端 API 客户端"""

import io
import time
import zipfile
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.infra.logging import get_logger

logger = get_logger("mineru")

DEFAULT_TIMEOUT = (10, 120)
DEFAULT_POLL_INTERVAL = 5
DEFAULT_MAX_POLL_ATTEMPTS = 600


def _create_session(
    retries: int = 5,
    backoff_factor: float = 2.0,
) -> requests.Session:
    retry = Retry(
        total=retries,
        connect=retries,
        read=retries,
        backoff_factor=backoff_factor,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST", "PUT"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def _request(
    session: requests.Session,
    method: str,
    url: str,
    timeout: tuple[int, int] = DEFAULT_TIMEOUT,
    **kwargs,
) -> requests.Response:
    try:
        return session.request(method, url, timeout=timeout, **kwargs)
    except requests.exceptions.ConnectionError as e:
        logger.warning("网络连接中断 (%s -> %s): %s", method, url, e)
        raise
    except requests.exceptions.Timeout as e:
        logger.warning("请求超时 (%s -> %s): %s", method, url, e)
        raise


def parse_local_pdf(
    pdf_path: str | Path,
    api_base: str,
    token: str,
    model_version: str = "vlm",
    poll_interval: int = DEFAULT_POLL_INTERVAL,
    max_poll_attempts: int = DEFAULT_MAX_POLL_ATTEMPTS,
    timeout: tuple[int, int] = DEFAULT_TIMEOUT,
) -> str:
    pdf_path = Path(pdf_path)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    session = _create_session()

    logger.info("申请上传链接: %s (model=%s)", pdf_path.name, model_version)
    resp = _request(
        session,
        "POST",
        f"{api_base}/file-urls/batch",
        headers=headers,
        json={
            "files": [{"name": pdf_path.name, "data_id": pdf_path.stem}],
            "model_version": model_version,
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    result = resp.json()
    if result["code"] != 0:
        raise RuntimeError(f"申请上传链接失败: {result['msg']}")

    batch_id = result["data"]["batch_id"]
    upload_url = result["data"]["file_urls"][0]
    logger.debug("batch_id=%s", batch_id)

    file_size = pdf_path.stat().st_size
    logger.info("上传文件 (%d bytes)...", file_size)
    with open(pdf_path, "rb") as f:
        upload_resp = _request(
            session, "PUT", upload_url, data=f, timeout=timeout
        )
    upload_resp.raise_for_status()
    logger.info("上传成功，batch_id: %s", batch_id)

    poll_url = f"{api_base}/extract-results/batch/{batch_id}"
    consecutive_errors = 0
    max_consecutive_errors = 10

    for poll_count in range(1, max_poll_attempts + 1):
        time.sleep(poll_interval)

        try:
            poll = _request(
                session, "GET", poll_url, headers=headers, timeout=timeout
            )
            poll.raise_for_status()
            consecutive_errors = 0
        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
        ) as e:
            consecutive_errors += 1
            logger.warning(
                "轮询失败 (%d/%d)，%ds 后重试: %s",
                consecutive_errors,
                max_consecutive_errors,
                poll_interval,
                e,
            )
            if consecutive_errors >= max_consecutive_errors:
                raise RuntimeError(
                    f"轮询连续失败 {max_consecutive_errors} 次，"
                    f"batch_id={batch_id} 仍可在 MinerU 后台查看任务状态"
                ) from e
            continue

        data = poll.json()["data"]
        item = data["extract_result"][0]
        state = item["state"]

        if state == "running" and "extract_progress" in item:
            progress = item["extract_progress"]
            logger.info(
                "解析中: %d/%d 页 (第 %d 次轮询)",
                progress.get("extracted_pages", 0),
                progress.get("total_pages", "?"),
                poll_count,
            )
        else:
            logger.info("状态: %s (第 %d 次轮询)", state, poll_count)

        if state == "done":
            zip_url = item["full_zip_url"]
            break
        elif state == "failed":
            raise RuntimeError(f"解析失败: {item.get('err_msg')}")
    else:
        raise RuntimeError(
            f"轮询超时（已等待约 {max_poll_attempts * poll_interval // 60} 分钟），"
            f"batch_id={batch_id}"
        )

    logger.info("下载解析结果...")
    zip_resp = _request(session, "GET", zip_url, timeout=timeout)
    zip_resp.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(zip_resp.content)) as zf:
        for name in zf.namelist():
            if name.endswith("full.md"):
                content = zf.read(name).decode("utf-8")
                logger.info("提取 full.md 成功，%d 字符", len(content))
                return content

    raise RuntimeError("zip 中未找到 full.md")
