

from django.contrib import admin



from .models import ConversationAnalysis, WordFrequency, POSDistribution


admin.site.register(ConversationAnalysis)
admin.site.register(WordFrequency)
admin.site.register(POSDistribution)