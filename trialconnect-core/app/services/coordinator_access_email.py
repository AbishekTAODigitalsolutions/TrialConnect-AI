from email.message import EmailMessage

from app.config import settings
def build_access_request_email(full_name: str, email: str) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = "Coordinator access approval requested"
    message["From"] = settings.SMTP_FROM_EMAIL
    message["To"] = settings.COORDINATOR_ADMIN_EMAIL
    message["Reply-To"] = email
    message.set_content(
        "A new coordinator has requested access to Clinical Connect AI.\n\n"
        f"Name: {full_name}\n"
        f"Email: {email}\n\n"
        "Sign in to the Coordinator Workbench as an admin and approve or reject "
        "the request under Settings > Coordinator access requests.\n"
        "The applicant's password is not included in this email."
    )
    return message
