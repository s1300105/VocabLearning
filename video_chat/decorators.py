from functools import wraps

from django.http import JsonResponse


def login_required_json(view_func):
    """fetch() から呼ばれる API 用の login_required。

    通常の login_required はログインページへリダイレクトするため、
    JSON を期待するフロントエンドではエラー内容が分からなくなる。
    代わりに 401 の JSON を返す。
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Authentication required'}, status=401)
        return view_func(request, *args, **kwargs)

    return wrapper
