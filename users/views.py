# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import json

from django.shortcuts import render, redirect, reverse
from django.http.response import HttpResponse
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.hashers import make_password
from django.db.models import Q
from django.views import View
#from django.contrib.auth.decorators import login_required
from extra.decorators import login_required
from django.core import serializers
from pure_pagination import Paginator, EmptyPage, PageNotAnInteger


from forms import LoginForm, UserAddForm
from utils.send_email import send_user_email

from models import UserProfile, MessageRecord

from utils.log import my_logger


class CustomBackend(ModelBackend):
    def authenticate(self, username=None, password=None, **kwargs):
        try:
            user = UserProfile.objects.get(Q(username=username) | Q(email=username))
            if user.check_password(password):
                return user
        except Exception as e:
            return None


class LoginView(View):
    def get(self, request):
        if request.user.is_anonymous.value:
            data = {

            }
            return render(request, "users/login.html", data)
        else:
            # 以下代码会导致循环重定向
            # callback_url = request.GET.get('next')
            # if callback_url:
            #     return redirect(callback_url)
            # else:
            return redirect(reverse('statistics_topology'))

    def post(self, request):
        login_form = LoginForm(request.POST)
        username = request.POST.get("username", "")
        password = request.POST.get('password', "")
        if login_form.is_valid():
            user = authenticate(username=username, password=password)
            if user is not None:
                if user.is_active:
                    login(request, user)
                    my_logger(level='info', message='登陆成功', username=request.user.name, path=request.path)
                    return redirect(reverse('statistics_topology'))
                else:
                    data = {
                        'msg': u'用户未激活',
                        "username": username,
                        "password": password,
                    }
                    my_logger(level='warning', message='未激活用户登陆尝试', username=username, path=request.path)
                    return render(request, "users/login.html", data)
            else:
                data = {
                    "msg": u'用户名或密码错误',
                    "username": username,
                    "password": password,
                }
                my_logger(level='warning', message='错误账号密码登陆尝试', username=username, path=request.path)
                return render(request, "users/login.html", data)
        else:
            data = {
                "msg": u'用户名或密码不符合规范',
                "username": username,
                "password": password,
                "login_form": login_form
            }
            return render(request, "users/login.html", data)


@login_required()
def my_logout(request):
    logout(request)
    data = {

    }
    return render(request, "users/login.html", data)


def test_email(request):
    send_user_email('173776778@qq.com', 'register')
    return HttpResponse('ok', status=200)


@login_required()
def user_add(request):
    data = {
        'sub_module': '7_1'
    }
    return render(request, 'users/user_add.html', data)


@login_required(identity=('operation', ))
def deal_user_add(request):

    print(request.POST)
    user_add_form = UserAddForm(request.POST)
    if user_add_form.is_valid():

        user_obj = UserProfile()
        user_obj.username = user_add_form.cleaned_data.get('username')
        user_obj.password = make_password(user_add_form.cleaned_data.get('password'))
        user_obj.name = user_add_form.cleaned_data.get('name')
        user_obj.email = '{}{}'.format(user_add_form.cleaned_data.get('email'), '@voole.com')
        user_obj.identity = user_add_form.cleaned_data.get('identity')
        user_obj.mobile_phone = user_add_form.cleaned_data.get('mobile_phone')
        user_obj.save()
        data = {
            'result_content': '用户添加成功，相关邮件已发送。'
        }
        return HttpResponse(json.dumps(data), content_type='application/json')
    else:
        data = {
            'result_content': '填写内容校验失败，请检查。'
        }
        return HttpResponse(json.dumps(data), content_type='application/json')


@login_required()
def messages(request):
    try:
        page = int(request.GET.get('page', 1))
        if page < 1:
            page = 1
    except ValueError:
        page = 1
    message_list = MessageRecord.objects.filter(send_to=request.user.id).order_by('-id')
    last_message = []
    for idx, message in enumerate(message_list):
        message_tmp = {}
        message_tmp['send_from'] = message.send_from.get()
        message_tmp['info'] = message
        print(message.id)
        last_message.append(message_tmp)
    p = Paginator(last_message, 15, request=request)
    try:
        record_list_in_pages = p.page(page)
    except EmptyPage:
        record_list_in_pages = p.page(1)
    data = {
        'sub_module': '7_2',
        'messages': record_list_in_pages
    }
    return render(request, 'users/message.html', data)


@login_required()
def new_message_by_ajax(request):
    message_list = MessageRecord.objects.filter(send_to=request.user.id, is_read=0).order_by('-id')[0:5]
    return HttpResponse(serializers.serialize("json", message_list), content_type='application/json')


@login_required()
def clear_unread_message_by_ajax(request):
    updated_message_number = MessageRecord.objects.filter(send_to=request.user.id, is_read=0).update(is_read=1)
    data = {
        'updated_message_number': updated_message_number
    }
    return HttpResponse(json.dumps(data), content_type='application/json')
