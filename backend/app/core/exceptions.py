"""统一业务异常。"""


class AppError(Exception):
    """业务异常基类，携带 HTTP 状态码与业务错误码。"""

    status_code = 400
    code = 1000

    def __init__(self, message: str, *, code: int | None = None, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code


class UnauthorizedError(AppError):
    status_code = 401
    code = 1401


class ForbiddenError(AppError):
    status_code = 403
    code = 1403


class NotFoundError(AppError):
    status_code = 404
    code = 1404


class ConflictError(AppError):
    status_code = 409
    code = 1409


class InvalidStateError(AppError):
    """任务状态流转非法。"""
    status_code = 409
    code = 1422


class ValidationError(AppError):
    status_code = 422
    code = 1422
