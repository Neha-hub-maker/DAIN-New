"""Replaceable institutional-verification boundary for the DAIN MVP."""

from app.core.config import settings


class InstitutionalEmailVerificationPrototype:
    """Prototype verifier based on domain ownership and a one-time email token.

    This is not DUNITE SSO. A real DUNITE provider can replace this class while
    the auth routes continue to use the same verification-token workflow.
    """

    def accepts(self, email: str) -> bool:
        domain = email.rsplit("@", 1)[-1].lower()
        return domain == settings.institutional_email_domain.lower()


institutional_verifier = InstitutionalEmailVerificationPrototype()
