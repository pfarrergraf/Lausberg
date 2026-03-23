from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests


APP_URL = "https://app.docupipe.ai"


def headers(api_key: str) -> dict[str, str]:
    return {
        "accept": "application/json",
        "content-type": "application/json",
        "X-API-Key": api_key,
    }


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def extract_text_payload(data: Any) -> str:
    if isinstance(data, str):
        return data
    if isinstance(data, dict):
        preferred_keys = [
            "text",
            "parsedText",
            "markdown",
            "content",
            "result",
            "data",
            "document",
        ]
        parts: list[str] = []
        for key in preferred_keys:
            if key in data:
                text = extract_text_payload(data[key])
                if text:
                    parts.append(text)
        if parts:
            return "\n\n".join(parts)
        generic_parts = []
        for key, value in data.items():
            text = extract_text_payload(value)
            if text:
                generic_parts.append(f"[{key}]\n{text}")
        return "\n\n".join(generic_parts)
    if isinstance(data, list):
        parts = [extract_text_payload(item) for item in data]
        return "\n\n".join(part for part in parts if part)
    return ""


def get_account_info(api_key: str) -> dict[str, Any]:
    response = requests.get(f"{APP_URL}/account", headers=headers(api_key), timeout=60)
    response.raise_for_status()
    return response.json()


def upload_document(api_key: str, input_path: Path, dataset: str | None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "document": {
            "file": {
                "contents": base64.b64encode(input_path.read_bytes()).decode("ascii"),
                "filename": input_path.name,
            }
        }
    }
    if dataset:
        payload["dataset"] = dataset

    response = requests.post(
        f"{APP_URL}/document",
        headers=headers(api_key),
        json=payload,
        timeout=180,
    )
    response.raise_for_status()
    return response.json()


def wait_for_job(api_key: str, job_id: str, poll_seconds: float, timeout_seconds: float) -> dict[str, Any]:
    start = time.perf_counter()
    last_payload: dict[str, Any] | None = None
    while True:
        response = requests.get(f"{APP_URL}/job/{job_id}", headers=headers(api_key), timeout=60)
        response.raise_for_status()
        payload = response.json()
        last_payload = payload
        status = str(payload.get("status", "")).lower()
        if status == "completed":
            return payload
        if status == "error":
            raise RuntimeError(f"DocuPipe job {job_id} failed: {json.dumps(payload, ensure_ascii=False)}")
        if (time.perf_counter() - start) > timeout_seconds:
            raise TimeoutError(f"Timed out waiting for DocuPipe job {job_id}; last payload: {json.dumps(last_payload, ensure_ascii=False)}")
        time.sleep(poll_seconds)


def get_document(api_key: str, document_id: str) -> dict[str, Any]:
    response = requests.get(f"{APP_URL}/document/{document_id}", headers=headers(api_key), timeout=180)
    response.raise_for_status()
    return response.json()


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload a small OCR sample to DocuPipe and save the results.")
    parser.add_argument("input_path", type=Path, help="Path to a local PDF/JPG/PNG sample")
    parser.add_argument("--output-dir", type=Path, required=True, help="Directory for JSON/text artifacts")
    parser.add_argument("--dataset", default=None, help="Optional DocuPipe dataset name")
    parser.add_argument("--api-key-env", default="DOCUPIPE_API_KEY", help="Environment variable containing the API key")
    parser.add_argument("--poll-seconds", type=float, default=2.0, help="Job polling interval in seconds")
    parser.add_argument("--timeout-seconds", type=float, default=600.0, help="Overall job timeout in seconds")
    args = parser.parse_args()

    api_key = os.environ.get(args.api_key_env)
    if not api_key:
        print(f"Missing API key in environment variable {args.api_key_env}", file=sys.stderr)
        return 2

    if not args.input_path.exists():
        print(f"Input file not found: {args.input_path}", file=sys.stderr)
        return 2

    args.output_dir.mkdir(parents=True, exist_ok=True)

    started_at = time.perf_counter()
    account = get_account_info(api_key)
    write_json(args.output_dir / "account.json", account)

    upload_started = time.perf_counter()
    upload_payload = upload_document(api_key, args.input_path, args.dataset)
    upload_elapsed_ms = int((time.perf_counter() - upload_started) * 1000)
    write_json(args.output_dir / "upload.json", upload_payload)

    document_id = upload_payload["documentId"]
    job_id = upload_payload["jobId"]

    job_payload = wait_for_job(
        api_key=api_key,
        job_id=job_id,
        poll_seconds=args.poll_seconds,
        timeout_seconds=args.timeout_seconds,
    )
    processing_elapsed_ms = int((time.perf_counter() - upload_started) * 1000)
    total_elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    write_json(args.output_dir / "job.json", job_payload)

    document_payload = get_document(api_key, document_id)
    write_json(args.output_dir / "document.json", document_payload)

    text_output = extract_text_payload(document_payload).strip()
    (args.output_dir / "document.txt").write_text(text_output, encoding="utf-8")
    (args.output_dir / "timing.json").write_text(
        json.dumps(
            {
                "upload_elapsed_ms": upload_elapsed_ms,
                "processing_elapsed_ms": processing_elapsed_ms,
                "total_elapsed_ms": total_elapsed_ms,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "document_id": document_id,
                "job_id": job_id,
                "output_dir": str(args.output_dir),
                "processing_elapsed_ms": processing_elapsed_ms,
                "text_length": len(text_output),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
