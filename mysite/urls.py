from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.staticfiles.storage import staticfiles_storage
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('word_learning/', include('word_learning.urls')),
    # path('english_conversation/', include('english_conversation.urls')),
    path('video_chat/', include('video_chat.urls')),
    path('conversation_analysis/', include('conversation_analysis.urls')),
    path('favicon.ico', RedirectView.as_view(
        url=staticfiles_storage.url('favicon.ico'),
        permanent=False,
    )),
]

if settings.DEBUG:
    # 開発サーバーで録音ファイルなどの MEDIA を配信する
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
