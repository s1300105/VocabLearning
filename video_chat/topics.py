"""一人用レッスンで出すお題（CEFR レベル別）"""
import random

SOLO_TOPICS = {
    'A1': [
        "Introduce yourself. What is your name, where do you live, and what do you like?",
        "Talk about your family.",
        "What do you usually eat for breakfast?",
        "Describe your room.",
        "What is your favorite season? Why?",
        "Talk about your best friend.",
    ],
    'A2': [
        "What did you do last weekend?",
        "Describe your hometown.",
        "Talk about your favorite food and how to make it.",
        "What do you do in your free time?",
        "Describe a typical day at your school or job.",
        "Where would you like to travel? Why?",
    ],
    'B1': [
        "Talk about a memorable trip you have taken.",
        "What are the good and bad points of living in a big city?",
        "Describe a person who has influenced you.",
        "What is a goal you want to achieve in the next five years?",
        "Talk about a book, movie or TV show you enjoyed recently.",
        "How do you usually deal with stress?",
    ],
    'B2': [
        "Should students be required to learn a second language? Explain your opinion.",
        "How has technology changed the way people communicate?",
        "Describe a difficult decision you made and how you made it.",
        "What are the advantages and disadvantages of working from home?",
        "Talk about an environmental problem in your country and possible solutions.",
        "Is social media good or bad for young people?",
    ],
    'C1': [
        "To what extent should governments regulate artificial intelligence?",
        "Discuss how globalization has affected local cultures.",
        "Describe a time you had to persuade someone, and what made your argument work.",
        "Is economic growth compatible with protecting the environment?",
        "What makes a good leader? Use examples to support your view.",
        "How should society balance privacy and security?",
    ],
    'C2': [
        "Evaluate the claim that history is written by the winners.",
        "Discuss whether universal basic income is a realistic policy.",
        "How does the language we speak shape the way we think?",
        "Should scientific research ever be limited for ethical reasons?",
        "Analyze the role of art in political movements.",
        "What responsibilities do wealthy nations have toward poorer ones?",
    ],
}

DEFAULT_LEVEL = 'B1'


def random_topic(cefr=None, exclude=None):
    """ユーザーの CEFR レベルに合ったお題をランダムに1つ返す（直前のお題は避ける）"""
    topics = SOLO_TOPICS.get(cefr) or SOLO_TOPICS[DEFAULT_LEVEL]
    candidates = [t for t in topics if t != exclude] or topics
    return random.choice(candidates)
