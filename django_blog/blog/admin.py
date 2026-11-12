from django.contrib import admin
from .models import Post, Membership, Message


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'kind', 'date_posted')
    list_filter = ('kind',)


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ('post', 'user', 'joined_at')


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('post', 'sender', 'body', 'created_at')
    list_filter = ('post',)
