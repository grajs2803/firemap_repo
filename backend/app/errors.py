from flask import jsonify, current_app
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.exceptions import HTTPException

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
    def handle_api_error(error):
        return jsonify({
            "error": {
                "code": error.code,
                "message": error.message,
                "details": error.details,
            }
        }), error.status_code

    @app.errorhandler(SQLAlchemyError)
    def handle_database_error(error):
        current_app.logger.exception("Database query failed")

        return jsonify({
            "error": {
                "code": "database_error",
                "message": "Unable to retrieve data at this time.",
            }
        }), 500

    @app.errorhandler(HTTPException)
    def handle_http_error(error):
        return jsonify({
            "error": {
                "code": error.name.lower().replace(" ", "_"),
                "message": error.description,
            }
        }), error.code

    @app.errorhandler(Exception)
    def handle_unexpected_error(error):
        current_app.logger.exception("Unexpected application error")

        return jsonify({
            "error": {
                "code": "internal_server_error",
                "message": "An unexpected server error occurred.",
            }
        }), 500