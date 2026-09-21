"""Windows-тосты без зависимостей: powershell + WinRT ToastText.

Тихо деградирует: нет PowerShell/WinRT — просто ничего не происходит.
"""
import subprocess


def toast(title, text=""):
    """Шлёт тост; любые ошибки глотаются — уведомление не имеет права ронять скан."""
    try:
        ps = (
            "$AppId='{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe';"
            "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, "
            "ContentType = WindowsRuntime] > $null;"
            "$T=[Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent("
            "[Windows.UI.Notifications.ToastTemplateType]::ToastText02);"
            "$x=$T.GetElementsByTagName('text');"
            "$x.Item(0).AppendChild($T.CreateTextNode('" + _esc(title) + "')) > $null;"
            "$x.Item(1).AppendChild($T.CreateTextNode('" + _esc(text) + "')) > $null;"
            "$N=[Windows.UI.Notifications.ToastNotification]::new($T);"
            "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($AppId).Show($N)"
        )
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                       capture_output=True, timeout=20)
        return True
    except Exception:                                  # noqa: BLE001 — тост не важнее данных
        return False


def _esc(text):
    """Одинарные кавычки в PowerShell удваиваются; переводы строк — пробелы."""
    return str(text or "").replace("'", "''").replace("\n", " ").replace("\r", " ")[:180]
