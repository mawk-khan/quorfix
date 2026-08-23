from unittest.mock import patch

from django.core.mail import EmailMessage

from apps.core.mail import DemoMailSinkBackend


class TestDemoMailSinkBackend:
    """apps.core.mail.DemoMailSinkBackend — only ever configured as
    EMAIL_BACKEND when settings.QUORFIX_DEMO_MODE is True (see
    config/settings/production.py). Never opens a real SMTP connection in
    these tests — the parent SMTPEmailBackend.send_messages is mocked out,
    since what's under test is the recipient-rewriting logic, not SMTP
    delivery itself (that's Django's own, already-tested code)."""

    def test_rewrites_recipients_to_the_configured_sink(self, settings):
        settings.QUORFIX_DEMO_MAIL_SINK = "ops@example.com"
        message = EmailMessage(
            subject="You've been invited",
            body="Accept your invitation: https://demo.quorfix.com/invitations/abc",
            from_email="webmaster@localhost",
            to=["attacker-controlled@external.example"],
            cc=["someone-else@external.example"],
            bcc=["hidden@external.example"],
        )
        backend = DemoMailSinkBackend()
        with patch(
            "django.core.mail.backends.smtp.EmailBackend.send_messages", return_value=1
        ) as mock_send:
            backend.send_messages([message])

        mock_send.assert_called_once()
        (sent_messages,) = mock_send.call_args[0]
        assert sent_messages[0].to == ["ops@example.com"]
        assert sent_messages[0].cc == []
        assert sent_messages[0].bcc == []

    def test_preserves_original_recipient_in_subject_for_operator_visibility(self, settings):
        settings.QUORFIX_DEMO_MAIL_SINK = "ops@example.com"
        message = EmailMessage(
            subject="You've been invited",
            body="...",
            from_email="webmaster@localhost",
            to=["someone@external.example"],
        )
        backend = DemoMailSinkBackend()
        with patch("django.core.mail.backends.smtp.EmailBackend.send_messages", return_value=1):
            backend.send_messages([message])
        assert "someone@external.example" in message.subject
        assert "You've been invited" in message.subject

    def test_rewrites_every_message_in_a_batch(self, settings):
        settings.QUORFIX_DEMO_MAIL_SINK = "ops@example.com"
        messages = [
            EmailMessage(
                subject=f"Message {i}",
                body="...",
                from_email="webmaster@localhost",
                to=[f"target-{i}@external.example"],
            )
            for i in range(3)
        ]
        backend = DemoMailSinkBackend()
        with patch(
            "django.core.mail.backends.smtp.EmailBackend.send_messages", return_value=3
        ) as mock_send:
            backend.send_messages(messages)

        (sent_messages,) = mock_send.call_args[0]
        assert all(m.to == ["ops@example.com"] for m in sent_messages)

    def test_body_content_is_not_altered(self, settings):
        settings.QUORFIX_DEMO_MAIL_SINK = "ops@example.com"
        message = EmailMessage(
            subject="Notice",
            body="This body must reach the sink unmodified.",
            from_email="webmaster@localhost",
            to=["someone@external.example"],
        )
        backend = DemoMailSinkBackend()
        with patch("django.core.mail.backends.smtp.EmailBackend.send_messages", return_value=1):
            backend.send_messages([message])
        assert message.body == "This body must reach the sink unmodified."
