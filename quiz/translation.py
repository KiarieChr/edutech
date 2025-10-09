from modeltranslation.translator import register, TranslationOptions
from modeltranslation.manager import MultilingualManager
from model_utils.managers import InheritanceManager
from .models import Quiz, Question, Choice,MCQuestion,EssayQuestion


# Create a custom manager that combines both managers
class MultilingualInheritanceManager(InheritanceManager, MultilingualManager):
    """
    Custom manager that combines InheritanceManager and MultilingualManager.
    This is necessary because Question model uses inheritance and translation.
    """
    use_for_related_fields = True
    
    def get_queryset(self):
        # Call both parent get_queryset methods
        qs = InheritanceManager.get_queryset(self)
        return qs


@register(Quiz)
class QuizTranslationOptions(TranslationOptions):
    fields = ("title", "description")


@register(Question)
class QuestionTranslationOptions(TranslationOptions):
    fields = ("content", "explanation")
    # Explicitly set the manager to use
    manager = MultilingualInheritanceManager()
@register(MCQuestion)
class MCQuestionTranslationOptions(TranslationOptions):
    pass  # Inherited fields from Question


@register(EssayQuestion)
class EssayQuestionTranslationOptions(TranslationOptions):
    pass  # Inherited fields from Question



@register(Choice)
class ChoiceTranslationOptions(TranslationOptions):
    fields = ("choice_text",)
