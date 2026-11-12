from . import views
from django.urls import path
from .views import PostListView, PostDetailView,PostCreateView, PostUpdateView, PostDeleteView

urlpatterns = [
    path('', PostListView.as_view(), name='blog-home'),
    path('post/<int:pk>/', PostDetailView.as_view(), name='post-detail'),
    path('post/<int:pk>/update', PostUpdateView.as_view(), name='post-update'),
    path('post/<int:pk>/delete', PostDeleteView.as_view(), name='post-delete'),
    path('post/new/', PostCreateView.as_view(), name='post-create'),
    path('post/<int:pk>/join/', views.join_post, name='post-join'),
    path('post/<int:pk>/leave/', views.leave_post, name='post-leave'),
    path('post/<int:pk>/chat/', views.chat, name='post-chat'),
    path('post/<int:pk>/chat/send/', views.send_message, name='post-chat-send'),
    path('post/<int:pk>/chat/messages/', views.chat_messages, name='post-chat-messages'),
    path('about/', views.about, name='blog-about'),
]
