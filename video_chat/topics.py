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


# 音読モードの例文（CEFR レベル別）。日本語話者が苦手な音（r と l、th、v と b、f、æ、
# 語末の子音、子音の連続）を多く含めている。すべての単語が CMU 発音辞書に載っていること。
READ_ALOUD_SENTENCES = {
    'A1': [
        "I really like rice and lemon tea.",
        "This is my brother's red bike.",
        "Three friends live near the river.",
        "I have a very big family.",
        "The light is on the left.",
        "Thank you for the lovely flowers.",
    ],
    'A2': [
        "Last weekend I visited my grandparents in the country.",
        "Could you pass me the salt and pepper, please?",
        "I usually walk to the station every morning.",
        "The weather was really warm yesterday.",
        "She loves playing the violin on Fridays.",
        "We watched a funny movie together.",
    ],
    'B1': [
        "I think the most important thing is to listen carefully.",
        "Traveling abroad helps you understand other cultures.",
        "The library is closed on the third Thursday of every month.",
        "My favorite season is fall because of the colorful leaves.",
        "He worked hard to improve his English vocabulary.",
        "Would you rather live in the city or the countryside?",
    ],
    'B2': [
        "Researchers believe that regular exercise improves both mental and physical health.",
        "Although the project was challenging, the team finished it ahead of schedule.",
        "Renewable energy will play a vital role in reducing carbon emissions.",
        "The flight was delayed for three hours because of thick fog.",
        "I would really appreciate it if you could reply by the end of the week.",
        "Without clear rules, online discussions can quickly become rude.",
    ],
    'C1': [
        "The government's response to the crisis was widely criticized for its lack of clarity.",
        "Artificial intelligence raises profound questions about privacy and responsibility.",
        "Thoroughly rehearsing a presentation is the best way to overcome nervousness.",
        "Rural communities often struggle to attract young workers and investment.",
        "Her argument was persuasive, although several of her assumptions were questionable.",
        "Rarely have I read a novel with such a vivid and believable world.",
    ],
    'C2': [
        "The theory's apparent elegance hides the extraordinary complexity of its assumptions.",
        "Notwithstanding these reservations, the proposal deserves serious consideration.",
        "Linguistic relativity remains a controversial hypothesis among cognitive scientists.",
        "The rhetoric of the campaign deliberately blurred the line between fact and opinion.",
        "Whether such reforms are viable depends largely on the political will to enforce them.",
        "The thoroughness of her research was reflected in every paragraph of the report.",
    ],
}


def random_sentence(cefr=None, exclude=None):
    """音読モード用の例文をランダムに1つ返す（直前の例文は避ける）"""
    sentences = READ_ALOUD_SENTENCES.get(cefr) or READ_ALOUD_SENTENCES[DEFAULT_LEVEL]
    candidates = [s for s in sentences if s != exclude] or sentences
    return random.choice(candidates)
