"""Demo-only outbound email sink. See settings.QUORFIX_DEMO_MODE,
docs/DEMO_DEPLOYMENT.md "Mail sink", and apps.core.checks (quorfix.E013).
"""

from django.conf import settings
from django.core.mail.backends.smtp import EmailBackend as SMTPEmailBackend


class DemoMailSinkBackend(SMTPEmailBackend):
    """Real SMTP delivery, but every message's recipients are replaced with
    a single operator-controlled sink address (QUORFIX_DEMO_MAIL_SINK)
    before sending — so the public demo can never deliver mail to an
    arbitrary external address, regardless of which code path constructed
    the message. Only ever configured as EMAIL_BACKEND when
    settings.QUORFIX_DEMO_MODE is True (see config/settings/production.py).

    Deliberately still a real SMTP backend rather than a non-delivering one
    (locmem/console) — those are flagged unsafe for production by
    apps.core.checks.check_email (quorfix.E006), and a demo deployment runs
    under the same production-hardened settings as a real one. Using genuine
    delivery to one fixed, operator-controlled mailbox is both safe and
    consistent with that requirement, and lets an operator actually verify
    demo-triggered mail (e.g. during a smoke test) rather than it vanishing
    silently.

    The original recipient list is preserved in the subject line for
    operator visibility; nothing about the message body is altered.
    """

    def send_messages(self, email_messages):
        sink = settings.QUORFIX_DEMO_MAIL_SINK
        for message in email_messages:
            original_recipients = ", ".join(message.to) or "(none)"
            message.subject = f"[demo original-to: {original_recipients}] {message.subject}"
            message.to = [sink]
            message.cc = []
            message.bcc = []
        return super().send_messages(email_messages)
