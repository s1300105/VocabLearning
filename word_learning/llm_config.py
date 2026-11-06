"""ローカル LLM (llama.cpp / Phi-3) を使った例文生成・英作文の出題と採点"""
import logging
import random
import threading
from functools import lru_cache
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)

DOCUMENT_DIR = Path(__file__).resolve().parent / 'document'
WRITING_SAMPLE_PATH = DOCUMENT_DIR / 'writting_sample.txt'
WRITING_PROMPT_PATH = DOCUMENT_DIR / 'writting_prompt.txt'

# サンプリング設定は Llama() のコンストラクタではなく生成時に渡す必要がある
CREATIVE_SAMPLING = {'temperature': 1.8, 'top_k': 100, 'top_p': 0.95}
EVAL_SAMPLING = {'temperature': 0.0, 'top_k': 3, 'top_p': 0.95}

# llama.cpp のモデルはスレッドセーフではないので、生成は直列に行う
_generate_lock = threading.Lock()

ERROR_MESSAGE = "An error occurred while generating the sentence."


@lru_cache(maxsize=2)
def _load_llm(n_ctx, n_gpu_layers):
    """モデルの読み込みは重いので、プロセス内で一度だけ行う"""
    from llama_cpp import Llama  # 重い依存なので使うときだけ import する

    return Llama(
        model_path=settings.LLM_MODEL_PATH,
        n_ctx=n_ctx,  # longer sequence lengths require much more resources
        n_threads=8,
        n_gpu_layers=n_gpu_layers,
        verbose=False,
    )


def get_llm():
    return _load_llm(n_ctx=1024, n_gpu_layers=35)


def get_llm_writting():
    return _load_llm(n_ctx=1024, n_gpu_layers=35)


def getllm_eval_wr():
    return _load_llm(n_ctx=2048, n_gpu_layers=0)


def _generate(llm, prompt, max_tokens, sampling):
    with _generate_lock:
        output = llm(
            f"<|user|>\n{prompt}<|end|>\n<|assistant|>",
            max_tokens=max_tokens,
            stop=["<|end|>"],
            echo=False,
            **sampling,
        )
    return output['choices'][0]['text'].strip()


def example_sentence(input_word, llm):
    try:
        prompt = f"Please write a sentence that contains the word {input_word}."
        return _generate(llm, prompt, max_tokens=32, sampling=CREATIVE_SAMPLING)
    except Exception:
        logger.exception("Error generating example sentence")
        return ERROR_MESSAGE


def writingquiz_llm(llm):
    try:
        prompt = (
            "Generate a single question in the same style as the following examples. "
            "Your response should contain only the new question, without any additional "
            "explanation or commentary: "
        )
        all_samples = WRITING_SAMPLE_PATH.read_text(encoding='utf-8').splitlines(keepends=True)
        samples = random.sample(all_samples, min(10, len(all_samples)))
        prompt += ''.join(samples)
        return _generate(llm, prompt, max_tokens=256, sampling=CREATIVE_SAMPLING)
    except Exception:
        logger.exception("Error generating writing quiz")
        return ERROR_MESSAGE


def llm_eval_wr(llm, content):
    try:
        prompt = WRITING_PROMPT_PATH.read_text(encoding='utf-8') + " " + content
        return _generate(llm, prompt, max_tokens=256, sampling=EVAL_SAMPLING)
    except Exception:
        logger.exception("Error evaluating writing answer")
        return ERROR_MESSAGE
