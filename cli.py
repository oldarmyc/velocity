#!/usr/bin/env python3

import asyncio
import configparser

import appdirs
import click
from velocity import Velocity


def read_config(ddi=None):
    config = configparser.ConfigParser()
    config_dir = appdirs.user_config_dir('rscloud')
    config.read(f'{config_dir}/config.ini')

    if ddi:
        username = config[ddi]['username']
        apikey = config[ddi]['apikey']
    else:
        first_section = config.sections()[0]
        username = config[first_section]['username']
        apikey = config[first_section]['apikey']
    
    return username, apikey


def review_errors(velocity):
    if len(velocity.errors) > 0:
        for error in velocity.errors:
            print(error)


@click.group()
@click.pass_context
@click.option('--ddi', envvar='RS_DDI')
def main(context, ddi):
    context.obj = read_config(ddi)


@main.command('upload')
@click.pass_obj
@click.argument('directory')
@click.argument('bucket')
@click.option('--region', prompt=True)
def upload(credentials, directory, bucket, region):
    username, apikey = credentials
    loop = asyncio.get_event_loop()
    velocity = Velocity(loop, username, apikey, region.upper())
    velocity.authenticate()
    velocity.create_container(bucket)
    loop.run_until_complete(velocity.process(bucket, 'upload', directory))
    loop.run_until_complete(velocity.close_session())
    loop.close()
    review_errors(velocity)


if __name__ == '__main__':
    main()
