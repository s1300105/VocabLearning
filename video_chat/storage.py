from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


@deconstructible
class PrivateMediaStorage(FileSystemStorage):
    """公開しない（MEDIA_URL で配信されない）ファイルの置き場所。

    一人用レッスンの録音などの個人データを保存し、所有者チェック付きのビュー経由でのみ返す。
    保存先は settings.PRIVATE_MEDIA_ROOT を毎回参照する（テストで override_settings できるように）。
    """

    def __init__(self):
        super().__init__(location=None, base_url=None)

    @property
    def base_location(self):
        return settings.PRIVATE_MEDIA_ROOT

    @property
    def location(self):
        return str(settings.PRIVATE_MEDIA_ROOT)

    @property
    def base_url(self):
        return None
