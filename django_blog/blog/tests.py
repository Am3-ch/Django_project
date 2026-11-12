from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Membership, Message, Post


@override_settings(ALLOWED_HOSTS=['testserver'],
                   STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
                             'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class MentorshipChatTests(TestCase):
    def setUp(self):
        self.author = User.objects.create_user('luffy', password='pw-test-123')
        self.joiner = User.objects.create_user('zoro', password='pw-test-123')
        self.outsider = User.objects.create_user('nami', password='pw-test-123')
        self.post = Post.objects.create(title='Looking for a mentor', content='python please',
                                        author=self.author, kind=Post.SEEKING)

    def url(self, name):
        return reverse(name, kwargs={'pk': self.post.pk})

    def send(self, body, as_json=True):
        headers = {'HTTP_X_REQUESTED_WITH': 'fetch'} if as_json else {}
        return self.client.post(self.url('post-chat-send'), {'body': body}, **headers)

    # ── Roles ──
    def test_roles_follow_post_kind(self):
        self.assertEqual(self.post.role_of(self.author), 'mentee')
        self.assertEqual(self.post.role_of(self.joiner), 'mentor')
        self.post.kind = Post.OFFERING
        self.assertEqual(self.post.role_of(self.author), 'mentor')
        self.assertEqual(self.post.role_of(self.joiner), 'mentee')

    # ── Joining ──
    def test_join_creates_membership_and_opens_chat(self):
        self.client.force_login(self.joiner)
        response = self.client.post(self.url('post-join'))
        self.assertRedirects(response, self.url('post-chat'))
        self.assertTrue(Membership.objects.filter(post=self.post, user=self.joiner).exists())

    def test_joining_twice_keeps_one_membership(self):
        self.client.force_login(self.joiner)
        self.client.post(self.url('post-join'))
        self.client.post(self.url('post-join'))
        self.assertEqual(Membership.objects.filter(post=self.post, user=self.joiner).count(), 1)

    def test_author_does_not_become_a_member(self):
        self.client.force_login(self.author)
        self.client.post(self.url('post-join'))
        self.assertFalse(Membership.objects.filter(post=self.post).exists())

    def test_join_requires_post_method(self):
        self.client.force_login(self.joiner)
        self.assertEqual(self.client.get(self.url('post-join')).status_code, 405)

    def test_leave_removes_membership(self):
        Membership.objects.create(post=self.post, user=self.joiner)
        self.client.force_login(self.joiner)
        self.client.post(self.url('post-leave'))
        self.assertFalse(Membership.objects.filter(post=self.post, user=self.joiner).exists())

    # ── Access control ──
    def test_outsider_is_sent_to_detail_page(self):
        self.client.force_login(self.outsider)
        self.assertRedirects(self.client.get(self.url('post-chat')), self.url('post-detail'))

    def test_outsider_cannot_send_or_poll(self):
        self.client.force_login(self.outsider)
        self.assertEqual(self.send('hi').status_code, 403)
        self.assertEqual(self.client.get(self.url('post-chat-messages')).status_code, 403)
        self.assertFalse(Message.objects.exists())

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(self.url('post-chat'))
        self.assertEqual(response.status_code, 302)
        self.assertNotIn('/chat/', response['Location'].split('?')[0])

    def test_author_and_member_can_open_chat(self):
        Membership.objects.create(post=self.post, user=self.joiner)
        for user in (self.author, self.joiner):
            self.client.force_login(user)
            self.assertEqual(self.client.get(self.url('post-chat')).status_code, 200)

    # ── Messages ──
    def test_send_and_poll(self):
        Membership.objects.create(post=self.post, user=self.joiner)
        self.client.force_login(self.joiner)
        response = self.send('  of course, what would you like to start with?  ')
        self.assertEqual(response.status_code, 200)
        sent = response.json()['message']
        self.assertEqual(sent['body'], 'of course, what would you like to start with?')
        self.assertTrue(sent['mine'])

        self.client.force_login(self.author)
        data = self.client.get(self.url('post-chat-messages'), {'after': 0}).json()
        self.assertEqual([m['id'] for m in data['messages']], [sent['id']])
        self.assertFalse(data['messages'][0]['mine'])
        self.assertTrue(data['live'])

        data = self.client.get(self.url('post-chat-messages'), {'after': sent['id']}).json()
        self.assertEqual(data['messages'], [])

    def test_empty_and_too_long_messages_are_rejected(self):
        self.client.force_login(self.author)
        self.assertEqual(self.send('   ').status_code, 400)
        self.assertEqual(self.send('x' * (Message.MAX_LENGTH + 1)).status_code, 400)
        self.assertFalse(Message.objects.exists())

    def test_send_without_javascript_redirects_back_to_chat(self):
        self.client.force_login(self.author)
        self.assertRedirects(self.send('hello', as_json=False), self.url('post-chat'))
        self.assertEqual(Message.objects.count(), 1)

    def test_message_html_is_escaped(self):
        Message.objects.create(post=self.post, sender=self.author, body='<script>alert(1)</script>')
        self.client.force_login(self.author)
        html = self.client.get(self.url('post-chat')).content.decode()
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;', html)
        self.assertNotIn('<script>alert(1)</script>', html)

    # ── Feed ──
    def test_feed_shows_member_count_with_role(self):
        Membership.objects.create(post=self.post, user=self.joiner)
        self.client.force_login(self.outsider)
        self.assertContains(self.client.get(reverse('blog-home')), '1 mentor')

    def test_create_post_with_kind(self):
        self.client.force_login(self.author)
        self.client.post(reverse('post-create'), {'kind': Post.OFFERING, 'title': 'Offering help',
                                                  'content': 'Django mentoring'})
        self.assertEqual(Post.objects.get(title='Offering help').kind, Post.OFFERING)
