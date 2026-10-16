from flask import jsonify


class APIError(Exception):
    status_code = 400

    def __init__(self, message, status_code=None, details=None):
        super().__init__(message)
        self.message = message
        self.details = details
        if status_code:
            self.status_code = status_code


class NotFound(APIError):
    status_code = 404


def register_error_handlers(app):
    @app.errorhandler(APIError)
    def handle_api_error(err):
        body = {"error": {"message": err.message}}
        if err.details:
            body["error"]["details"] = err.details
        return jsonify(body), err.status_code

    @app.errorhandler(404)
    def handle_404(_):
        return jsonify({"error": {"message": "route not found"}}), 404