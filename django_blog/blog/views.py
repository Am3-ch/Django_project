from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Count, Max
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView

from .forms import PostForm
from .models import Post, Membership, Message


class PostListView(LoginRequiredMixin, ListView):
    model = Post
    template_name = 'blog/home.html' # <app>/<model>_<viewtype>.html
    context_object_name = 'posts'

    def get_queryset(self):
        return (Post.objects
                .select_related('author')
                .annotate(member_count=Count('memberships', distinct=True),
                          last_message_at=Max('messages__created_at'))
                .order_by('-date_posted'))


class PostDetailView(DetailView):
    model = Post

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        post = self.object
        user = self.request.user
        context['member_count'] = post.memberships.count()
        context['is_author'] = user == post.author
        context['can_chat'] = post.can_chat(user)
        return context


class PostCreateView(LoginRequiredMixin ,CreateView):
    model = Post
    form_class = PostForm

    def form_valid(self, form):
        form.instance.author = self.request.user
        return super().form_valid(form)

class PostUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = Post
    form_class = PostForm

    def form_valid(self, form):
        form.instance.author = self.request.user
        return super().form_valid(form)

    def test_func(self):
        post = self.get_object()
        if self.request.user == post.author:
            return True
        return False

class PostDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = Post
    success_url = reverse_lazy('blog-home')

    def test_func(self):
        post = self.get_object()
        if self.request.user == post.author:
            return True
        return False


def about(request):
    return render(request, 'blog/about.html', { 'title': 'About' })


# ── Mentorship group chat ──

def _time_label(moment):
    local = timezone.localtime(moment)
    if local.date() == timezone.localdate():
        return local.strftime('%H:%M')
    return local.strftime('%b %d, %H:%M')


def _message_data(message, user):
    return {
        'id': message.id,
        'body': message.body,
        'sender': message.sender.username,
        'initial': message.sender.username[:1].upper(),
        'mine': message.sender_id == user.id,
        'time': _time_label(message.created_at),
    }


@login_required
@require_POST
def join_post(request, pk):
    post = get_object_or_404(Post, pk=pk)
    if request.user != post.author:
        _, created = Membership.objects.get_or_create(post=post, user=request.user)
        if created:
            messages.success(request, f'You joined "{post.title}" as a {post.member_role}.')
    return redirect('post-chat', pk=post.pk)


@login_required
@require_POST
def leave_post(request, pk):
    post = get_object_or_404(Post, pk=pk)
    deleted, _ = Membership.objects.filter(post=post, user=request.user).delete()
    if deleted:
        messages.info(request, f'You left "{post.title}".')
    return redirect('post-detail', pk=post.pk)


@login_required
def chat(request, pk):
    post = get_object_or_404(Post.objects.select_related('author'), pk=pk)
    if not post.can_chat(request.user):
        messages.info(request, 'Join this mentorship to open its group chat.')
        return redirect('post-detail', pk=post.pk)

    memberships = post.memberships.select_related('user')
    participants = [{'user': post.author, 'role': post.author_role}]
    participants += [{'user': m.user, 'role': post.member_role} for m in memberships]
    first_join = memberships.first()

    chat_messages = list(post.messages.select_related('sender').order_by('-created_at', '-id')[:200])
    chat_messages.reverse()

    return render(request, 'blog/chat.html', {
        'title': post.title,
        'post': post,
        'participants': participants,
        'started_at': first_join.joined_at if first_join else None,
        'chat_messages': [_message_data(m, request.user) for m in chat_messages],
        'last_id': chat_messages[-1].id if chat_messages else 0,
        'max_length': Message.MAX_LENGTH,
        'is_author': request.user == post.author,
    })


@login_required
@require_POST
def send_message(request, pk):
    post = get_object_or_404(Post, pk=pk)
    if not post.can_chat(request.user):
        return HttpResponseForbidden('Join this mentorship first.')

    body = request.POST.get('body', '').strip()
    wants_json = request.headers.get('x-requested-with') == 'fetch'
    error = None
    if not body:
        error = 'Message is empty.'
    elif len(body) > Message.MAX_LENGTH:
        error = f'Messages can be at most {Message.MAX_LENGTH} characters.'

    if error:
        if wants_json:
            return JsonResponse({'error': error}, status=400)
        messages.warning(request, error)
        return redirect('post-chat', pk=post.pk)

    message = Message.objects.create(post=post, sender=request.user, body=body)
    if wants_json:
        return JsonResponse({'message': _message_data(message, request.user)})
    return redirect('post-chat', pk=post.pk)  # fallback when JavaScript is off


@login_required
@require_GET
def chat_messages(request, pk):
    """Polled by the chat page: returns messages newer than ?after=<id>."""
    post = get_object_or_404(Post, pk=pk)
    if not post.can_chat(request.user):
        return JsonResponse({'error': 'forbidden'}, status=403)
    try:
        after = int(request.GET.get('after', 0))
    except ValueError:
        after = 0
    new = post.messages.select_related('sender').filter(id__gt=after).order_by('id')[:100]
    return JsonResponse({
        'messages': [_message_data(m, request.user) for m in new],
        'live': post.is_live,
    })
