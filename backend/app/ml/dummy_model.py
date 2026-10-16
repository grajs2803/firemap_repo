import math


FEATURES = [
    "fwi",
    "ndvi",
    "slope",
    "dist_to_road_m",
    "rainfall_mm",
]

STATS = {
    "fwi": (12.0, 8.0),
    "ndvi": (0.55, 0.15),
    "slope": (12.0, 8.0),
    "dist_to_road_m": (2500.0, 1500.0),
    "rainfall_mm": (3.0, 5.0),
}

WEIGHTS = {
    "fwi": 1.1,
    "ndvi": -0.7,
    "slope": 0.4,
    "dist_to_road_m": -0.3,
    "rainfall_mm": -0.5,
}

BIAS = -3.0


def _sigmoid(x):
    return 1.0 / (1.0 + math.exp(-x))


def risk_level(probability):
    if probability < 0.10:
        return "low"
    elif probability < 0.25:
        return "moderate"
    elif probability < 0.50:
        return "high"
    return "extreme"


class DummyRiskModel:
    version = "dummy-0.1.0"
    trained_at = "2026-01-01T00:00:00Z"
    feature_list = FEATURES
    metrics = {
        "auc_pr": None,
        "note": "Synthetic weights; no model was trained.",
    }
    is_dummy = True

    @staticmethod
    def _z(row):
        result = {}

        for feature in FEATURES:
            mean, std = STATS[feature]
            value = row.get(feature)

            result[feature] = (
                0.0 if value is None else (value - mean) / std
            )

        return result

    def predict_proba(self, row):
        z = self._z(row)

        logit = BIAS + sum(
            WEIGHTS[feature] * z[feature]
            for feature in FEATURES
        )

        return _sigmoid(logit)

    def explain(self, row):
        z = self._z(row)

        contributions = {
            feature: {
                "value": row.get(feature),
                "shap": round(
                    WEIGHTS[feature] * z[feature], 4
                ),
            }
            for feature in FEATURES
        }

        logit = BIAS + sum(
            WEIGHTS[feature] * z[feature]
            for feature in FEATURES
        )

        return {
            "probability": round(_sigmoid(logit), 4),
            "logit": round(logit, 4),
            "base_value": BIAS,
            "contributions": contributions,
        }