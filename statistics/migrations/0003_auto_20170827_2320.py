# -*- coding: utf-8 -*-
# Generated by Django 1.11.3 on 2017-08-27 15:20
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('statistics', '0002_auto_20170816_0044'),
    ]

    operations = [
        migrations.AlterField(
            model_name='backupinstance',
            name='login_instance_account',
            field=models.CharField(default='root', max_length=20, verbose_name='\u767b\u9646\u5b9e\u4f8b\u8d26\u53f7'),
        ),
        migrations.AlterField(
            model_name='backupinstance',
            name='port',
            field=models.IntegerField(default=22, verbose_name='\u5b9e\u4f8bssh\u7aef\u53e3'),
        ),
    ]
