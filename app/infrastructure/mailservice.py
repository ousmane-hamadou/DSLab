import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Configuration du logger pour DSLab
logger = logging.getLogger("dslab.infrastructure.mail")


class SmtpMailService:
    def __init__(self):
        # Récupération sécurisée depuis les variables d'environnement
        self.smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", 587))
        self.sender_email = os.getenv("SENDER_EMAIL")
        # Mot de passe d'application
        self.password = os.getenv("SENDER_PASSWORD")

    def send_approval(self, to_email: str, user_uuid: str, url: str):
        """Envoie l'email contenant l'URL de session via ngrok."""

        # Vérification si les identifiants sont présents
        if not self.sender_email or not self.password:
            logger.error(
                "Configuration SMTP manquante : vérifiez SENDER_EMAIL et SENDER_PASSWORD")
            return

        message = MIMEMultipart()
        message["From"] = self.sender_email
        message["To"] = to_email
        message["Subject"] = "Accès DSLab : Votre session est prête"

        body = f"""
        Bonjour,

        Votre demande de ressources sur DSLab a été approuvée.
        
        Vous pouvez accéder à votre environnement de calcul via le lien sécurisé suivant :
        {url}

        Identifiant de session : {user_uuid}
        
        Cordialement,
        L'administration DSLab.
        """

        message.attach(MIMEText(body, "plain"))

        try:
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.sender_email, self.password)
                server.send_message(message)

            logger.info(f"Email d'approbation envoyé avec succès à {to_email}")

        except smtplib.SMTPAuthenticationError:
            logger.error(
                f"Échec de l'authentification SMTP pour {self.sender_email}. Vérifiez le mot de passe d'application.")
        except Exception as e:
            logger.exception(
                f"Erreur inattendue lors de l'envoi de l'email à {to_email} : {e}")
