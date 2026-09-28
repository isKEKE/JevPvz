"""Load the local TypeSafe API configuration without exposing credentials."""

from __future__ import annotations

import math
import os
from contextlib import contextmanager
from dataclasses import dataclass
from os import PathLike
from typing import Iterator

from dotenv import load_dotenv


class JevConfigurationError(RuntimeError):
    """Raised when the required key or configured proxy is unavailable."""


DEFAULT_MODEL_NAME = "jev-latest"
DEFAULT_NOUL_CANDIDATE_THRESHOLD = 0.6
DEFAULT_ROUTER_CONFIDENCE_THRESHOLD = 0.6
DEFAULT_ACTION_CONFIDENCE_THRESHOLD = 0.6
NOUL_CANDIDATE_THRESHOLD_ENV = "JEV_NOUL_CANDIDATE_THRESHOLD"
ROUTER_CONFIDENCE_THRESHOLD_ENV = "JEV_ROUTER_CONFIDENCE_THRESHOLD"
ACTION_CONFIDENCE_THRESHOLD_ENV = "JEV_ACTION_CONFIDENCE_THRESHOLD"


@dataclass(frozen=True)
class JevThresholds:
    noul_candidate_threshold: float
    router_confidence_threshold: float
    action_confidence_threshold: float


@dataclass(frozen=True)
class RuntimeConfig:
    """The runtime configuration read and validated once before the client starts.

    Only the presence of each credential source is recorded; credential values stay
    in ``os.environ`` and are never copied into this object.
    """

    thresholds: JevThresholds
    model_name: str
    api_key_present: bool
    http_proxy_present: bool
    https_proxy_present: bool


def load_typesafe_environment(dotenv_path: str | PathLike[str] | None = None) -> None:
    """Load .env values without overriding the caller's process environment."""
    _load_validated_environment(dotenv_path)


def load_runtime_config(dotenv_path: str | PathLike[str] | None = None) -> RuntimeConfig:
    """Read, validate, and freeze the runtime configuration before the first request."""
    return RuntimeConfig(
        thresholds=_load_validated_environment(dotenv_path),
        model_name=DEFAULT_MODEL_NAME,
        api_key_present=bool(os.environ.get("TYPESAFE_API_KEY", "").strip()),
        http_proxy_present=bool(os.environ.get("HTTP_PROXY", "").strip()),
        https_proxy_present=bool(os.environ.get("HTTPS_PROXY", "").strip()),
    )


def _load_validated_environment(dotenv_path: str | PathLike[str] | None) -> JevThresholds:
    if dotenv_path is None:
        load_dotenv(override=False)
    else:
        load_dotenv(dotenv_path=dotenv_path, override=False)

    if not os.environ.get("TYPESAFE_API_KEY", "").strip():
        raise JevConfigurationError("TYPESAFE_API_KEY is not configured.")
    if not os.environ.get("HTTP_PROXY", "").strip() or not os.environ.get("HTTPS_PROXY", "").strip():
        raise JevConfigurationError("Both HTTP_PROXY and HTTPS_PROXY must be configured for TypeSafe access.")
    return load_jev_thresholds()


def load_jev_thresholds() -> JevThresholds:
    """Load the independent Noul, Router Choice, and Action Choice gates."""
    return JevThresholds(
        noul_candidate_threshold=_configured_threshold(
            NOUL_CANDIDATE_THRESHOLD_ENV, DEFAULT_NOUL_CANDIDATE_THRESHOLD
        ),
        router_confidence_threshold=_configured_threshold(
            ROUTER_CONFIDENCE_THRESHOLD_ENV, DEFAULT_ROUTER_CONFIDENCE_THRESHOLD
        ),
        action_confidence_threshold=_configured_threshold(
            ACTION_CONFIDENCE_THRESHOLD_ENV, DEFAULT_ACTION_CONFIDENCE_THRESHOLD
        ),
    )


def _configured_threshold(env_name: str, default: float) -> float:
    raw = os.environ.get(env_name)
    if raw is None or not raw.strip():
        return default
    try:
        threshold = float(raw.strip())
    except (TypeError, ValueError):
        raise JevConfigurationError(f"{env_name} must be a number from 0 through 1.") from None
    if not math.isfinite(threshold) or not 0.0 <= threshold <= 1.0:
        raise JevConfigurationError(f"{env_name} must be a number from 0 through 1.")
    return threshold


@contextmanager
def use_configured_http_proxy_fallback() -> Iterator[None]:
    """Prevent an inherited SOCKS ALL_PROXY from overriding the configured HTTP proxies."""
    fallback = os.environ["HTTPS_PROXY"]
    keys = ("ALL_PROXY", "all_proxy")
    original = {key: (key in os.environ, os.environ.get(key)) for key in keys}
    try:
        for key in keys:
            os.environ[key] = fallback
        yield
    finally:
        for key, (was_set, value) in original.items():
            if was_set and value is not None:
                os.environ[key] = value
            else:
                os.environ.pop(key, None)


@contextmanager
def runtime_environment(dotenv_path: str | PathLike[str] | None = None) -> Iterator[RuntimeConfig]:
    """Hold one frozen runtime configuration and the proxy fallback for a client lifetime.

    The environment is configured once on entry and restored to the pre-entry values
    once on exit, so requests issued during the lifetime never mutate ``os.environ``.
    """
    config = load_runtime_config(dotenv_path)
    with use_configured_http_proxy_fallback():
        yield config


__all__ = [
    "ACTION_CONFIDENCE_THRESHOLD_ENV",
    "DEFAULT_ACTION_CONFIDENCE_THRESHOLD",
    "DEFAULT_MODEL_NAME",
    "DEFAULT_NOUL_CANDIDATE_THRESHOLD",
    "DEFAULT_ROUTER_CONFIDENCE_THRESHOLD",
    "JevConfigurationError",
    "JevThresholds",
    "NOUL_CANDIDATE_THRESHOLD_ENV",
    "ROUTER_CONFIDENCE_THRESHOLD_ENV",
    "RuntimeConfig",
    "load_jev_thresholds",
    "load_runtime_config",
    "load_typesafe_environment",
    "runtime_environment",
    "use_configured_http_proxy_fallback",
]
