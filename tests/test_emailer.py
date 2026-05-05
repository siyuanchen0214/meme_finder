from meme_finder.config import EmailConfig
from meme_finder.emailer import send_email


def test_send_email_smtp_flow(mocker):
    mock_ctor = mocker.patch("meme_finder.emailer.smtplib.SMTP")
    mock_server = mocker.MagicMock()
    mock_ctor.return_value.__enter__.return_value = mock_server

    cfg = EmailConfig(
        smtp_host="h",
        smtp_port=587,
        smtp_username="u",
        smtp_password="p",
        email_from="a@a.com",
        email_to="b@b.com",
    )
    send_email(cfg, subject="Subj", body_markdown="Body\n")

    mock_ctor.assert_called_once_with("h", 587)
    mock_server.starttls.assert_called_once()
    mock_server.login.assert_called_once_with("u", "p")
    mock_server.send_message.assert_called_once()
