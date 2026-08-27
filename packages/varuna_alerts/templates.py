from typing import Dict, Any

class AlertTemplates:
    @staticmethod
    def format_alert(template_id: str, context: Dict[str, Any]) -> str:
        return f"Alert {template_id} with context {context}"
