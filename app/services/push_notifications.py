#push_notifications
def send_push_notification(
    token: str,
    title: str,
    body: str
):
    """
    TEMPORAIRE
    Ici plus tard : Firebase Cloud Messaging (FCM)
    """
    print("\n=========================")
    print("[PUSH NOTIFICATION]")
    print(f"TO: {token}")
    print(f"TITLE: {title}")
    print(f"BODY: {body}")
    print("=========================\n")


def send_sms_notification(
    phone_number: str,
    message: str
):
    """
    TEMPORAIRE
    Ici plus tard : Twilio / Vonage / autre fournisseur SMS
    """
    print("\n=========================")
    print("[SMS NOTIFICATION]")
    print(f"TO: {phone_number}")
    print(f"BODY: {message}")
    print("=========================\n")