# -*- coding: utf-8 -*-
import httplib as http
import logging

from modularodm.exceptions import ValidationValueError
import framework
from framework import request, User, status
from framework.auth.decorators import collect_auth
from framework.auth.utils import parse_name
from framework.exceptions import HTTPError
from framework.auth.exceptions import DuplicateEmailError
from ..decorators import must_not_be_registration, must_be_valid_project, \
    must_be_contributor, must_be_contributor_or_public
from framework import forms
from framework.auth.forms import SetEmailAndPasswordForm

from website import settings, mails, language
from website.filters import gravatar
from website.models import Node
from website.profile import utils


logger = logging.getLogger(__name__)


@collect_auth
@must_be_valid_project
def get_node_contributors_abbrev(**kwargs):

    auth = kwargs.get('auth')
    node_to_use = kwargs['node'] or kwargs['project']

    max_count = kwargs.get('max_count', 3)
    if 'user_ids' in kwargs:
        users = [
            User.load(user_id) for user_id in kwargs['user_ids']
            if user_id in node_to_use.contributors
        ]
    else:
        users = node_to_use.contributors

    if not node_to_use.can_view(auth):
        raise HTTPError(http.FORBIDDEN)

    contributors = []

    n_contributors = len(users)
    others_count, others_suffix = '', ''

    for index, user in enumerate(users[:max_count]):

        if index == max_count - 1 and len(users) > max_count:
            separator = ' &'
            others_count = n_contributors - 3
            others_suffix = 's' if others_count > 1 else ''
        elif index == len(users) - 1:
            separator = ''
        elif index == len(users) - 2:
            separator = ' &'
        else:
            separator = ','

        contributors.append({
            'user_id': user._primary_key,
            'separator': separator,
        })

    return {
        'contributors': contributors,
        'others_count': others_count,
        'others_suffix': others_suffix,
    }

# TODO: Almost identical to utils.serialize_user. Remove duplication.
def _add_contributor_json(user):

    return {
        'fullname': user.fullname,
        'id': user._primary_key,
        'registered': user.is_registered,
        'active': user.is_active(),
        'gravatar': gravatar(
            user, use_ssl=True,
            size=settings.GRAVATAR_SIZE_ADD_CONTRIBUTOR
        ),
    }


def serialized_contributors(node):

    data = []
    for contrib in node.contributors:
        serialized = utils.serialize_user(contrib)
        serialized['fullname'] = contrib.display_full_name(node=node)
        data.append(serialized)
    return data


@collect_auth
@must_be_valid_project
def get_contributors(**kwargs):

    auth = kwargs.get('auth')
    node = kwargs['node'] or kwargs['project']

    if not node.can_view(auth):
        raise HTTPError(http.FORBIDDEN)

    contribs = serialized_contributors(node)
    return {'contributors': contribs}


@collect_auth
@must_be_valid_project
def get_contributors_from_parent(**kwargs):

    auth = kwargs.get('auth')
    node_to_use = kwargs['node'] or kwargs['project']

    parent = node_to_use.node__parent[0] if node_to_use.node__parent else None
    if not parent:
        raise HTTPError(http.BAD_REQUEST)

    if not node_to_use.can_view(auth):
        raise HTTPError(http.FORBIDDEN)

    contribs = [
        _add_contributor_json(contrib)
        for contrib in parent.contributors
        if contrib not in node_to_use.contributors
    ]

    return {'contributors': contribs}


@must_be_contributor
def get_recently_added_contributors(**kwargs):

    auth = kwargs.get('auth')
    node_to_use = kwargs['node'] or kwargs['project']

    if not node_to_use.can_view(auth):
        raise HTTPError(http.FORBIDDEN)

    contribs = [
        _add_contributor_json(contrib)
        for contrib in auth.user.recently_added
        if contrib.is_active()
        if contrib not in node_to_use.contributors
    ]

    return {'contributors': contribs}


@must_be_valid_project  # returns project
@must_be_contributor  # returns user, project
@must_not_be_registration
def project_before_remove_contributor(**kwargs):

    node_to_use = kwargs['node'] or kwargs['project']

    contributor = User.load(request.json.get('id'))
    prompts = node_to_use.callback(
        'before_remove_contributor', removed=contributor,
    )

    return {'prompts': prompts}


@must_be_valid_project  # returns project
@must_be_contributor  # returns user, project
@must_not_be_registration
def project_removecontributor(**kwargs):

    node_to_use = kwargs['node'] or kwargs['project']
    auth = kwargs['auth']

    if request.json['id'].startswith('nr-'):
        outcome = node_to_use.remove_nonregistered_contributor(
            auth, request.json['name'],
            request.json['id'].replace('nr-', '')
        )
    else:
        contributor = User.load(request.json['id'])
        if contributor is None:
            raise HTTPError(http.BAD_REQUEST)
        outcome = node_to_use.remove_contributor(
            contributor=contributor, auth=auth,
        )
    if outcome:
        framework.status.push_status_message('Contributor removed', 'info')
        return {'status': 'success'}
    raise HTTPError(http.BAD_REQUEST)

# TODO: Make this a Node method? But it depends on the request data format,
# so maybe not
# TODO: TEST ME
def add_contributors_from_dicts(node, user_dicts, auth, email_unregistered=True):
    """View helper that adds contributors from a list of serialized users. The
    users in the list may be registered or unregistered users.

    e.g. ``[{'id': 'abc123', 'registered': True, 'fullname': ..},
            {'id': None, 'registered': False, 'fullname'...},
            {'id': '123ab', 'registered': False, 'fullname': ...}]

    :param Node node: The node to add contributors to
    :param list(dict) user_dicts: List of serialized users in the format above.
    :param Auth auth:
    :param bool email_unregistered: Whether to email the claim email(s)
        to unregistered users.
    """

    # Add the registered contributors
    contribs = []
    for contrib_dict in user_dicts:
        if contrib_dict['id']:
            user = User.load(contrib_dict['id'])
        else:
            email = contrib_dict['email']
            fullname = contrib_dict['fullname']
            try:
                user = User.create_unregistered(
                    fullname=fullname,
                    email=email)
                user.save()
            except ValidationValueError:
                user = framework.auth.get_user(username=contrib_dict['email'])

        if not user.is_registered:
            user.add_unclaimed_record(node=node,
                referrer=auth.user,
                email=contrib_dict['email'],
                given_name=contrib_dict['fullname'])
            user.save()
            if contrib_dict['email'] and email_unregistered:
                send_claim_email(contrib_dict['email'], user, node, notify=True)
        contribs.append(user)
    node.add_contributors(contributors=contribs, auth=auth)


@must_be_valid_project # returns project
@must_be_contributor  # returns user, project
@must_not_be_registration
def project_addcontributors_post(**kwargs):
    """ Add contributors to a node. """
    node = kwargs['node'] or kwargs['project']
    auth = kwargs['auth']
    user_dicts = request.json.get('users', [])
    node_ids = request.json.get('node_ids', [])
    add_contributors_from_dicts(node, user_dicts, auth=auth)
    node.save()
    for node_id in node_ids:
        child = Node.load(node_id)
        add_contributors_from_dicts(child, user_dicts,
            auth=auth, email_unregistered=False)  # Only email unreg users once
        child.save()
    return {'status': 'success'}, 201


def send_claim_email(email, user, node, notify=True):
    """Send an email for claiming a user account. Either sends to the given email
    or the referrer's email, depending on the email address provided.

    :param str email: The address given in the claim user form
    :param User user: The User record to claim.
    :param Node node: The node where the user claimed their account.
    :param bool notify: If True and an email is sent to the referrer, an email
        will also be sent to the invited user about their pending verification.
    """
    invited_email = email.lower().strip()
    unclaimed_record = user.get_unclaimed_record(node._primary_key)
    referrer = User.load(unclaimed_record['referrer_id'])
    claim_url = user.get_claim_url(node._primary_key, external=True)
    # If given email is the same provided by user, just send to that email
    if unclaimed_record.get('email', None) == invited_email:
        mail_tpl = mails.INVITE
        to_addr = invited_email
    else:  # Otherwise have the referrer forward the email to the user
        mail_tpl = mails.FORWARD_INVITE
        to_addr = referrer.username
        if notify:
            mails.send_mail(invited_email, mails.PENDING_VERIFICATION,
                user=user,
                referrer=referrer,
                fullname=unclaimed_record['name'],
                node=node
            )
    mails.send_mail(to_addr, mail_tpl,
        user=user,
        referrer=referrer,
        node=node,
        claim_url=claim_url,
        email=invited_email,
        fullname=unclaimed_record['name']
    )
    return to_addr


def verify_claim_token(user, token, pid):
    """View helper that checks that a claim token for a given user and node ID
    is valid. If not valid, throws an error with custom error messages.
    """
    # if token is invalid, throw an error
    if not user.verify_claim_token(token=token, project_id=pid):
        if user.is_registered:
            error_data = {
                'message_short': 'User has already been claimed.',
                'message_long': 'Please <a href="/login/">log in</a> to continue.'}
        else:
            error_data = {
                'message_short': 'Invalid claim URL.',
                'message_long': 'The URL you entered is invalid.'}
        raise HTTPError(400, data=error_data)
    return True


def claim_user_form(**kwargs):
    """View for rendering the set password page for a claimed user.

    Must have ``token`` as a querystring argument.

    Renders the set password form, validates it, and sets the user's password.
    """
    uid, pid = kwargs['uid'], kwargs['pid']
    token = request.form.get('token') or request.args.get('token')
    # There shouldn't be a user logged in
    if framework.auth.get_current_user():
        logout_url = framework.url_for('OsfWebRenderer__auth_logout')
        error_data = {'message_short': 'You are already logged in.',
            'message_long': ('To claim this account, you must first '
                '<a href={0}>log out.</a>'.format(logout_url))}
        raise HTTPError(400, data=error_data)
    user = framework.auth.get_user(id=uid)
    # user ID is invalid. Unregistered user is not in database
    if not user:
        raise HTTPError(400)
    verify_claim_token(user, token, pid)
    unclaimed_record = user.unclaimed_records[pid]
    email = unclaimed_record['email']
    form = SetEmailAndPasswordForm(request.form, token=token)
    if request.method == 'POST':
        if form.validate():
            username = form.username.data
            password = form.password.data
            user.register(username=username, password=password)
            del user.unclaimed_records[pid]
            user.save()
            # Authenticate user and redirect to project page
            response = framework.redirect('/settings/')
            node = Node.load(pid)
            status.push_status_message(language.CLAIMED_CONTRIBUTOR.format(node=node),
                'success')
            return framework.auth.authenticate(user, response)
        else:
            forms.push_errors_to_status(form.errors)
    parsed_name = parse_name(user.fullname)
    is_json_request = request.content_type == 'application/json'
    return {
        'firstname': parsed_name['given_name'],
        'email': email,
        'fullname': user.fullname,
        'form': forms.utils.jsonify(form) if is_json_request else form,
    }


def serialize_unregistered(fullname, email):
    """Serializes an unregistered user.
    """
    user = framework.auth.get_user(username=email)
    if user is None:
        serialized = {
            'fullname': fullname,
            'id': None,
            'registered': False,
            'active': False,
            'gravatar': gravatar(email, use_ssl=True,
                size=settings.GRAVATAR_SIZE_ADD_CONTRIBUTOR),
            'email': email
        }
    else:
        serialized = _add_contributor_json(user)
        serialized['fullname']
        serialized['email'] = email
    return serialized


@must_be_valid_project
@must_be_contributor
@must_not_be_registration
def invite_contributor_post(**kwargs):
    """API view for inviting an unregistered user.
    Expects JSON arguments with 'fullname' (required) and email (not required).
    """
    node = kwargs['node'] or kwargs['project']
    fullname = request.json.get('fullname').strip()
    email = request.json.get('email')
    if email:
        email = email.lower().strip()
    if not fullname:
        return {'status': 400, 'message': 'Must provide fullname'}, 400
    # Check if email is in the database
    user = framework.auth.get_user(username=email)
    if user:
        if user.is_registered:
            msg = 'User is already in database. Please go back and try your search again.'
            return {'status': 400, 'message': msg}, 400
        elif node.is_contributor(user):
            msg = 'User with this email address is already a contributor to this project.'
            return {'status': 400, 'message': msg}, 400
        else:
            serialized = _add_contributor_json(user)
            # use correct display name
            serialized['fullname'] = fullname
            serialized['email'] = email
    else:
        # Create a placeholder
        serialized = serialize_unregistered(fullname, email)
    return {'status': 'success', 'contributor': serialized}


@must_be_contributor_or_public
def claim_user_post(**kwargs):
    """View for claiming a user from the X-editable form on a project page.
    """
    reqdata = request.json
    user = User.load(reqdata['pk'])
    email = reqdata['value'].lower().strip()
    node = kwargs['node'] or kwargs['project']
    send_claim_email(email, user, node, notify=True)
    unclaimed_data = user.get_unclaimed_record(node._primary_key)
    return {
        'status': 'success',
        'fullname': unclaimed_data['name'],
        'email': email,
    }
