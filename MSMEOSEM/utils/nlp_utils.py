import nltk
import re
import string
import json
from nltk.corpus import stopwords
from sklearn.feature_extraction.text import TfidfVectorizer
from deep_translator import GoogleTranslator
from config import Config

# ---------- Initialize NLTK ----------
nltk.data.path.append(Config.NLTK_DATA_PATH)
stop_words = set(stopwords.words("english"))

# ---------- Text preprocessing ----------
def preprocess_text(text):
    """Lowercase, remove punctuation, remove stopwords."""
    text = text.lower().translate(str.maketrans("", "", string.punctuation))
    tokens = [word for word in text.split() if word not in stop_words]
    return " ".join(tokens)

def normalize(text):
    """Remove non-alphanumeric characters and lowercase."""
    return re.sub(r"\W+", "", text.lower())

# ---------- Intent loading ----------
def load_intents():
    """Load intents JSON from file."""
    try:
        with open(Config.INTENTS_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception as e:
        print(f"Error loading intents: {e}")
        return []

# ---------- Translation ----------
def translate_text(text, target_lang="hi"):
    """Translate text to target language (hi or en)."""
    try:
        return GoogleTranslator(source="auto", target=target_lang).translate(text)
    except Exception as e:
        print(f"Translation error: {e}")
        return text

# ---------- NLP initialization ----------
def initialize_nlp():
    """Preprocess intents, build TF-IDF corpus, and store English responses."""
    intents_data = load_intents()
    corpus, tags, responses = [], [], {}

    for item in intents_data:
        if all(k in item for k in ("intent", "patterns", "responses")):
            intent = item["intent"]
            processed_patterns = [preprocess_text(p) for p in item["patterns"]]
            corpus.extend(processed_patterns)
            tags.extend([intent] * len(processed_patterns))
            responses[intent] = item["responses"]

    if not corpus:
        return None, None, [], {}

    vectorizer = TfidfVectorizer()
    X = vectorizer.fit_transform(corpus)
    return vectorizer, X, tags, responses
