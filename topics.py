"""
نظام المواضيع الـ31 لتعليم اللغة الإنجليزية
يحتوي على جميع المواضيع المطلوبة مع تفاصيل كل موضوع
"""

from typing import Dict, List, Any
from dataclasses import dataclass

@dataclass
class TopicSection:
    """قسم فرعي داخل الموضوع"""
    name: str
    description: str
    key_points: List[str]
    examples: List[str]
    exercises: List[str]

@dataclass
class EnglishTopic:
    """موضوع تعليمي في اللغة الإنجليزية"""
    id: int
    name: str
    arabic_name: str
    description: str
    difficulty_level: str  # beginner, intermediate, advanced
    estimated_duration: int  # بالدقائق
    prerequisites: List[int]  # معرفات المواضيع المطلوبة مسبقاً
    sections: List[TopicSection]
    key_vocabulary: List[str]
    learning_objectives: List[str]
    assessment_questions: List[Dict[str, Any]]

# تعريف جميع المواضيع الـ31
ENGLISH_TOPICS = {
    1: EnglishTopic(
        id=1,
        name="Nouns",
        arabic_name="الأسماء",
        description="Learn about different types of nouns and their usage in English",
        difficulty_level="beginner",
        estimated_duration=45,
        prerequisites=[],
        sections=[
            TopicSection(
                name="Types of Nouns",
                description="Different categories of nouns",
                key_points=[
                    "Common nouns vs Proper nouns",
                    "Concrete nouns vs Abstract nouns", 
                    "Countable vs Uncountable nouns",
                    "Collective nouns"
                ],
                examples=[],
                exercises=[]
            ),
            TopicSection(
                name="Noun Functions",
                description="How nouns work in sentences",
                key_points=[
                    "Subject of sentence",
                    "Object of verb",
                    "Object of preposition",
                    "Complement"
                ],
                examples=[],
                exercises=[]
            )
        ],
        key_vocabulary=[
            "noun", "subject", "object", "proper", "common", "abstract", 
            "concrete", "countable", "uncountable", "collective"
        ],
        learning_objectives=[
            "Identify different types of nouns",
            "Use nouns correctly in sentences",
            "Understand noun functions",
            "Distinguish countable from uncountable nouns"
        ],
        assessment_questions=[
            {
                "question": "What type of noun is 'happiness'?",
                "options": ["Common", "Proper", "Abstract", "Collective"],
                "correct": 2,
                "explanation": "Happiness is an abstract noun because it represents an idea or feeling"
            }
        ]
    ),

    2: EnglishTopic(
        id=2,
        name="Definite and Indefinite Articles",
        arabic_name="أدوات التعريف والتنكير",
        description="Master the usage of 'a', 'an', and 'the' in English",
        difficulty_level="beginner",
        estimated_duration=30,
        prerequisites=[1],
        sections=[
            TopicSection(
                name="Indefinite Articles (a, an)",
                description="When and how to use 'a' and 'an'",
                key_points=[
                    "Use 'a' before consonant sounds",
                    "Use 'an' before vowel sounds",
                    "Used with singular countable nouns",
                    "Express 'one' or 'any'"
                ],
                examples=[],
                exercises=[]
            ),
            TopicSection(
                name="Definite Article (the)",
                description="When to use 'the'",
                key_points=[
                    "Specific or known items",
                    "Unique things",
                    "Previously mentioned items",
                    "Superlatives and ordinals"
                ],
                examples=[],
                exercises=[]
            )
        ],
        key_vocabulary=[
            "article", "definite", "indefinite", "consonant", "vowel", 
            "specific", "general", "unique", "countable"
        ],
        learning_objectives=[
            "Use 'a' and 'an' correctly",
            "Know when to use 'the'",
            "Understand article rules",
            "Apply articles in speech and writing"
        ],
        assessment_questions=[
            {
                "question": "Which article goes before 'university'?",
                "options": ["a", "an", "the", "no article"],
                "correct": 0,
                "explanation": "University starts with a consonant sound /ju/, so we use 'a'"
            }
        ]
    ),

    3: EnglishTopic(
        id=3,
        name="Adjectives",
        arabic_name="الصفات",
        description="Learn about adjectives and their various uses",
        difficulty_level="beginner",
        estimated_duration=50,
        prerequisites=[1, 2],
        sections=[
            TopicSection(
                name="Types of Adjectives",
                description="Different categories of adjectives",
                key_points=[
                    "Descriptive adjectives",
                    "Demonstrative adjectives",
                    "Possessive adjectives",
                    "Quantitative adjectives"
                ],
                examples=[],
                exercises=[]
            ),
            TopicSection(
                name="Adjective Order",
                description="The correct order when using multiple adjectives",
                key_points=[
                    "Opinion before fact",
                    "Size before age before color",
                    "Origin before material",
                    "Purpose adjectives come last"
                ],
                examples=[],
                exercises=[]
            )
        ],
        key_vocabulary=[
            "adjective", "descriptive", "demonstrative", "possessive", 
            "quantitative", "opinion", "fact", "order", "modify"
        ],
        learning_objectives=[
            "Identify different types of adjectives",
            "Use adjectives to describe nouns",
            "Apply correct adjective order",
            "Enhance descriptive language"
        ],
        assessment_questions=[
            {
                "question": "What is the correct order: 'car sports red new expensive'?",
                "options": [
                    "expensive new red sports car",
                    "new expensive red sports car", 
                    "red new expensive sports car",
                    "sports red new expensive car"
                ],
                "correct": 0,
                "explanation": "Opinion (expensive) + age (new) + color (red) + purpose (sports) + noun (car)"
            }
        ]
    ),

    4: EnglishTopic(
        id=4,
        name="Personal Pronouns",
        arabic_name="الضمائر الشخصية",
        description="Master personal pronouns and their different forms",
        difficulty_level="beginner",
        estimated_duration=40,
        prerequisites=[1],
        sections=[
            TopicSection(
                name="Subject Pronouns",
                description="Pronouns that act as subjects",
                key_points=[
                    "I, you, he, she, it, we, they",
                    "Replace the subject noun",
                    "Come before the verb",
                    "Never omit in English"
                ],
                examples=[],
                exercises=[]
            ),
            TopicSection(
                name="Object Pronouns",
                description="Pronouns that receive the action",
                key_points=[
                    "me, you, him, her, it, us, them",
                    "Come after verbs or prepositions",
                    "Receive the action",
                    "Different from subject pronouns"
                ],
                examples=[],
                exercises=[]
            )
        ],
        key_vocabulary=[
            "pronoun", "subject", "object", "personal", "replace", 
            "verb", "preposition", "action", "receive"
        ],
        learning_objectives=[
            "Use subject pronouns correctly",
            "Apply object pronouns appropriately", 
            "Distinguish between subject and object forms",
            "Improve sentence fluency"
        ],
        assessment_questions=[
            {
                "question": "Choose the correct pronoun: 'Give the book to ___'",
                "options": ["I", "me", "my", "mine"],
                "correct": 1,
                "explanation": "After prepositions like 'to', we use object pronouns (me)"
            }
        ]
    ),

    5: EnglishTopic(
        id=5,
        name="Verbs",
        arabic_name="الأفعال",
        description="Understand verbs and their basic forms and functions",
        difficulty_level="intermediate",
        estimated_duration=60,
        prerequisites=[1, 4],
        sections=[
            TopicSection(
                name="Types of Verbs",
                description="Different categories of verbs",
                key_points=[
                    "Action verbs (run, eat, write)",
                    "Linking verbs (be, seem, become)",
                    "Helping verbs (have, will, can)",
                    "Transitive vs Intransitive"
                ],
                examples=[],
                exercises=[]
            ),
            TopicSection(
                name="Verb Forms",
                description="Base, past, and past participle forms",
                key_points=[
                    "Base form (infinitive)",
                    "Past tense form",
                    "Past participle",
                    "Present participle (-ing form)"
                ],
                examples=[],
                exercises=[]
            )
        ],
        key_vocabulary=[
            "verb", "action", "linking", "helping", "auxiliary", "transitive", 
            "intransitive", "base form", "past tense", "participle", "irregular"
        ],
        learning_objectives=[
            "Identify different types of verbs",
            "Use verb forms correctly",
            "Understand transitive vs intransitive",
            "Master irregular verb forms"
        ],
        assessment_questions=[
            {
                "question": "What is the past participle of 'write'?",
                "options": ["wrote", "written", "writing", "writes"],
                "correct": 1,
                "explanation": "The past participle of 'write' is 'written' (used with have/has/had)"
            }
        ]
    )
}

# إضافة باقي المواضيع (6-31) - سأضيف بعضها كأمثلة
ENGLISH_TOPICS.update({
    6: EnglishTopic(
        id=6,
        name="More about Verbs",
        arabic_name="المزيد عن الأفعال",
        description="Advanced verb concepts and usage",
        difficulty_level="intermediate",
        estimated_duration=55,
        prerequisites=[5],
        sections=[
            TopicSection(
                name="Phrasal Verbs",
                description="Verbs with prepositions or adverbs",
                key_points=[
                    "Separable phrasal verbs",
                    "Inseparable phrasal verbs", 
                    "Common phrasal verbs",
                    "Meaning changes with particles"
                ],
                examples=[],
                exercises=[]
            )
        ],
        key_vocabulary=["phrasal verb", "particle", "separable", "inseparable", "preposition", "adverb"],
        learning_objectives=[
            "Understand phrasal verb structure",
            "Use common phrasal verbs correctly",
            "Distinguish separable from inseparable"
        ],
        assessment_questions=[]
    ),

    7: EnglishTopic(
        id=7,
        name="Auxiliary Verbs",
        arabic_name="الأفعال المساعدة",
        description="Learn about helping verbs and their functions",
        difficulty_level="intermediate", 
        estimated_duration=45,
        prerequisites=[5],
        sections=[
            TopicSection(
                name="Primary Auxiliaries",
                description="Be, Have, Do as helping verbs",
                key_points=[
                    "Be: continuous tenses, passive voice",
                    "Have: perfect tenses",
                    "Do: questions, negatives, emphasis"
                ],
                examples=[],
                exercises=[]
            )
        ],
        key_vocabulary=["auxiliary", "helping verb", "primary", "modal", "tense", "passive", "emphasis"],
        learning_objectives=[
            "Use auxiliary verbs correctly",
            "Form questions and negatives",
            "Understand auxiliary functions"
        ],
        assessment_questions=[]
    )
})

# دالة للحصول على موضوع بالمعرف
def get_topic_by_id(topic_id: int) -> EnglishTopic:
    """الحصول على موضوع بالمعرف"""
    return ENGLISH_TOPICS.get(topic_id)

# دالة للحصول على المواضيع حسب المستوى
def get_topics_by_level(level: str) -> List[EnglishTopic]:
    """الحصول على المواضيع حسب مستوى الصعوبة"""
    return [topic for topic in ENGLISH_TOPICS.values() if topic.difficulty_level == level]

# دالة للحصول على المواضيع المتاحة للمستخدم
def get_available_topics(completed_topics: List[int]) -> List[EnglishTopic]:
    """الحصول على المواضيع المتاحة بناءً على المواضيع المكتملة"""
    available = []
    for topic in ENGLISH_TOPICS.values():
        # التحقق من أن جميع المتطلبات المسبقة مكتملة
        if all(prereq in completed_topics for prereq in topic.prerequisites):
            available.append(topic)
    return available

# دالة للحصول على الموضوع التالي المقترح
def get_next_suggested_topic(completed_topics: List[int]) -> EnglishTopic:
    """اقتراح الموضوع التالي بناءً على التقدم"""
    available = get_available_topics(completed_topics)
    if not available:
        return None
    
    # ترتيب حسب المعرف (التسلسل الطبيعي)
    available.sort(key=lambda x: x.id)
    return available[0] if available else None

# دالة للبحث في المواضيع
def search_topics(query: str) -> List[EnglishTopic]:
    """البحث في المواضيع بالاسم أو الوصف"""
    query = query.lower()
    results = []
    for topic in ENGLISH_TOPICS.values():
        if (query in topic.name.lower() or 
            query in topic.arabic_name.lower() or 
            query in topic.description.lower()):
            results.append(topic)
    return results

# إحصائيات المواضيع
def get_topics_stats() -> Dict[str, Any]:
    """إحصائيات عامة عن المواضيع"""
    topics = list(ENGLISH_TOPICS.values())
    return {
        "total_topics": len(topics),
        "beginner_topics": len([t for t in topics if t.difficulty_level == "beginner"]),
        "intermediate_topics": len([t for t in topics if t.difficulty_level == "intermediate"]), 
        "advanced_topics": len([t for t in topics if t.difficulty_level == "advanced"]),
        "total_estimated_hours": sum(t.estimated_duration for t in topics) / 60,
        "average_duration": sum(t.estimated_duration for t in topics) / len(topics) if topics else 0
    }

# قائمة سريعة بأسماء المواضيع للمرجع
TOPIC_NAMES = {
    1: "Nouns", 2: "Definite and Indefinite Articles", 3: "Adjectives", 
    4: "Personal Pronouns", 5: "Verbs", 6: "More about Verbs", 
    7: "Auxiliary Verbs", 8: "The past progressive tense", 9: "Passive voice",
    10: "Adverbs", 11: "Contractions", 12: "Plurals", 13: "Punctuation",
    14: "Infinitives and gerunds", 15: "Relative pronouns", 16: "Reflexive pronouns",
    17: "Possession", 18: "Prepositions", 19: "More about prepositions",
    20: "Capitalization", 21: "Subjunctive mood", 22: "Comparatives and superlatives",
    23: "Conjunctions", 24: "Interrogatives", 25: "Negation", 26: "Numbers",
    27: "Conversation: Introductions, opinions, descriptions",
    28: "Conversation: Openers, appointments, needs", 
    29: "Conversation: Future events, narration, electronic communication",
    30: "Some Important Contrasts", 31: "Phrasal verbs"
}
