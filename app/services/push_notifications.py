#push_notifications.py
import os
import json
import logging
from typing import Optional

import firebase_admin
from firebase_admin import credentials, messaging

logger = logging.getLogger("push_notifications")

# =========================
# INITIALISATION FIREBASE
# =========================

def _init_firebase():
    try:
        # Déjà initialisé ?
        firebase_admin.get_app()
        return
    except ValueError:
        pass

    firebase_json_str = os.getenv("FIREBASE_CREDENTIALS_JSON")

    if not firebase_json_str:
        logger.warning("⚠️ FIREBASE_CREDENTIALS_JSON est manquant dans le .env")
        return

    try:
        cred_dict = json.loads(firebase_json_str)
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
        logger.info("Firebase Admin initialisé avec succès")
    except Exception as e:
        logger.error(f"Erreur d'initialisation Firebase : {e}")


_init_firebase()


# =========================
# ENVOI DE PUSH
# =========================

def send_push_notification(
    token: str,
    title: str,
    body: str,
    data: Optional[dict] = None
):
    """
    Envoie une notification push via Firebase Cloud Messaging.
    """
    if not token:
        logger.warning("Token vide, push ignoré")
        return

    try:
        # Les valeurs de data doivent être des strings
        data_payload = None
        if data:
            data_payload = {str(k): str(v) for k, v in data.items()}

        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body
            ),
            data=data_payload,
            token=token
        )

        response = messaging.send(message)
        logger.info(f"Push envoyé → {token[:20]}... | response: {response}")
        return response

    except messaging.UnregisteredError:
        logger.warning(f"Token invalide / désinscrit : {token[:30]}...")
    except Exception as e:
        logger.error(f"Échec envoi push vers {token[:20]}... : {e}")
