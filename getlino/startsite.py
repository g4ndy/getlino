# Copyright 2019 Rumma & Ko Ltd
# License: BSD (see file COPYING for details)

import os
import shutil
import secrets
import click

from os.path import join

from .utils import APPNAMES, FOUND_CONFIG_FILES, DEFAULTSECTION, USE_NGINX
from .utils import DB_ENGINES, BATCH_HELP, REPOS_DICT, KNOWN_REPOS
from .utils import Installer, ifroot

SITES_AVAILABLE = '/etc/nginx/sites-available'
SITES_ENABLED = '/etc/nginx/sites-enabled'

COOKIECUTTER_URL = "https://github.com/lino-framework/cookiecutter-startsite"

UWSGI_SUPERVISOR_CONF = """
# generated by getlino
[program:{prjname}-uwsgi]
command = /usr/bin/uwsgi --ini {project_dir}/nginx/uwsgi.ini
user = {usergroup}
umask = 0002
"""

LINOD_SUPERVISOR_CONF = """
# generated by getlino
[program:linod-{prjname}]
command={project_dir}/linod.sh
user = {usergroup}
umask = 0002
"""
LINOD_SH = """
#!/bin/bash
set -e  # exit on error
PRJ={project_dir}
. $PRJ/{env_link}/bin/activate
exec python $PRJ/manage.py linod
"""

def default_shared_env():
    return DEFAULTSECTION.get('shared_env')


@click.command()
@click.argument('appname', metavar="APPNAME", type=click.Choice(APPNAMES))
@click.argument('prjname')
@click.option('--batch/--no-batch', default=False, help=BATCH_HELP)
@click.option('--dev-repos', default='',
              help="List of packages for which to install development version")
@click.option('--shared-env', default=default_shared_env,
              help="Directory with shared virtualenv")
@click.pass_context
def startsite(ctx, appname, prjname, batch, dev_repos, shared_env):
    """
    Create a new Lino site.

    Two mandatory arguments must be given:

    APPNAME : The application to run on the new site.

    SITENAME : The internal name for the new site. It must be unique for this
    Lino server. We recommend lower-case only and maybe digits but no "-" or
    "_". Examples:  foo, foo2, mysite, first,


    """ # .format(appnames=' '.join(APPNAMES))

    # if len(FOUND_CONFIG_FILES) == 0:
    #     raise click.UsageError(
    #         "This server is not yet configured. Did you run `sudo -H getlino configure`?")

    i = Installer(batch)

    # if os.path.exists(prjpath):
    #     raise click.UsageError("Project directory {} already exists.".format(prjpath))

    # prod = DEFAULTSECTION.getboolean('prod')
    # contrib = DEFAULTSECTION.getboolean('contrib')
    sites_base = DEFAULTSECTION.get('sites_base')
    local_prefix = DEFAULTSECTION.get('local_prefix')
    python_path_root = join(sites_base, local_prefix)
    project_dir = join(python_path_root, prjname)
    # shared_env = DEFAULTSECTION.get('shared_env')
    admin_name = DEFAULTSECTION.get('admin_name')
    admin_email = DEFAULTSECTION.get('admin_email')
    server_domain = prjname + "." + DEFAULTSECTION.get('server_domain')
    server_url = ("https://" if DEFAULTSECTION.getboolean('https') else "http://") \
                 + server_domain
    secret_key = secrets.token_urlsafe(20)

    db_engine = None
    for e in DB_ENGINES:
        if DEFAULTSECTION.get('db_engine') == e.name:
            db_engine = e
            break
    if db_engine is None:
        raise click.ClickException(
            "Invalid --db-engine '{}'. Run getlino configure.".format(
                DEFAULTSECTION.get('db_engine')))
    db_host = DEFAULTSECTION.get('db_host')
    db_port = DEFAULTSECTION.get('db_port') or db_engine.default_port

    usergroup = DEFAULTSECTION.get('usergroup')

    app = REPOS_DICT.get(appname, None)
    if app is None:
        raise click.ClickException("Invalid application nickname '{}'".format(appname))
    if not app.settings_module:
        raise click.ClickException("{} is a library, not an application".format(appname))

    front_end = REPOS_DICT.get(DEFAULTSECTION.get('front_end'), None)
    if front_end is None:
        raise click.ClickException("Invalid front_end name '{}''".format(front_end))

    i.check_usergroup(usergroup)

    if dev_repos:
        for k in dev_repos.split():
            repo = REPOS_DICT.get(k, None)
            if repo is None or not repo.git_repo:
                nicknames = ' '.join([r.nickname for r in KNOWN_REPOS if r.git_repo])
                raise click.ClickException(
                    "Invalid repository name {}. "
                    "Allowed names are one or more of ({})".format(
                        k, nicknames))

    if not i.check_overwrite(project_dir):
        raise click.Abort()

    # if not i.asroot and not shared_env:
    #     raise click.ClickException(
    #         "Cannot startsite in a development environment without a shared-env!")

    app_package = app.package_name
    # app_package = app.settings_module.split('.')[0]
    repo_nickname = app.git_repo.split('/')[-1]

    context = {}
    context.update(DEFAULTSECTION)
    pip_packages = set()
    if True:  # not shared_env:
        if app.nickname not in dev_repos:
            pip_packages.add(app.package_name)
        if front_end.nickname not in dev_repos:
            pip_packages.add(front_end.package_name)

        # 20190803 not needed:
        # for nickname in ("lino", "xl"):
        #     if nickname not in dev_repos:
        #         pip_packages.add(REPOS_DICT[nickname].package_name)

    for pkgname in db_engine.python_packages.split():
        pip_packages.add(pkgname)

    context.update({
        "prjname": prjname,
        "appname": appname,
        "project_dir": project_dir,
        "repo_nickname": repo_nickname,
        "app_package": app_package,
        "app_settings_module": app.settings_module,
        "django_settings_module": "{}.{}.settings".format(local_prefix, prjname),
        "server_domain":server_domain,
        "server_url": server_url,
        "dev_packages": ' '.join([a.nickname for a in KNOWN_REPOS if a.nickname in dev_repos]),
        "pip_packages": ' '.join(pip_packages),
        "db_name": prjname,
        "python_path": sites_base,
        "usergroup": usergroup
    })

    click.echo(
        'Create a new Lino {appname} site into {project_dir}'.format(
            **context))

    db_user = DEFAULTSECTION.get('db_user')
    shared_user = False
    if db_user:
        db_password = DEFAULTSECTION.get('db_password')
        shared_user = True
    else:
        db_user = prjname
        db_password = secrets.token_urlsafe(8)
        if not batch:
            if db_engine.name != "sqlite3":
                click.echo(
                    "User credentials (for {db_engine} on {db_host}:{db_port}):".format(
                        **context))
                db_user = click.prompt("- user name", default=db_user)
                db_password = click.prompt("- user password", default=db_password)
                db_port = click.prompt("- port", default=db_port)
                db_host = click.prompt("- host name", default=db_host)

    if not batch:
        shared_env = click.prompt("Shared virtualenv", default=shared_env)
        # if asroot:
        #     server_url = click.prompt("Server URL ", default=server_url)
        #     admin_name = click.prompt("Administrator's full name", default=admin_name)
        #     admin_email = click.prompt("Administrator's full name", default=admin_email)
        secret_key = click.prompt("Site's secret key", default=secret_key)

    context.update({
        "db_host": db_host,
        "db_port": db_port,
        "db_user": db_user,
        "db_password": db_password,
        "secret_key": secret_key,
    })

    if not i.yes_or_no("OK to create {} with above options?".format(project_dir)):
        raise click.Abort()

    os.umask(0o002)

    os.makedirs(project_dir, exist_ok=True)
    i.jinja_write(join(project_dir, "settings.py"), **context)
    i.jinja_write(join(project_dir, "manage.py"), **context)
    # pull.sh script is now in the virtualenv's bin folder
    #i.jinja_write(join(project_dir, "pull.sh"), **context)
    if ifroot():
        i.jinja_write(join(project_dir, "make_snapshot.sh"), **context)
        i.make_file_executable(join(project_dir, "make_snapshot.sh"))
        os.makedirs(join(project_dir, "nginx"), exist_ok=True)
        i.jinja_write(join(project_dir, "wsgi.py"), **context)
        i.jinja_write(join(project_dir, "nginx", "uwsgi.ini"), **context)
        i.jinja_write(join(project_dir, "nginx", "uwsgi_params"), **context)

        logdir = join(DEFAULTSECTION.get("log_base"), prjname)
        os.makedirs(logdir, exist_ok=True)
        with i.override_batch(True):
            i.check_permissions(logdir)
            os.symlink(logdir, join(project_dir, 'log'))
            i.write_logrotate_conf(
                'lino-{}.conf'.format(prjname),
                join(logdir, "lino.log"))

        backups_base_dir = join(DEFAULTSECTION.get("backups_base"), prjname)
        os.makedirs(backups_base_dir, exist_ok=True)
        with i.override_batch(True):
            i.check_permissions(backups_base_dir)


    if DEFAULTSECTION.getboolean('linod'):
        i.write_file(
            join(project_dir, 'linod.sh'),
            LINOD_SH.format(**context), executable=True)
        if ifroot():
            i.write_supervisor_conf(
                'linod_{}.conf'.format(prjname),
                LINOD_SUPERVISOR_CONF.format(**context))
            i.must_restart('supervisor')

    os.makedirs(join(project_dir, 'media'), exist_ok=True)

    if shared_env:
        envdir = shared_env
    else:
        envdir = join(project_dir, DEFAULTSECTION.get('env_link'))

    i.check_virtualenv(envdir, context)

    if shared_env:
        os.symlink(envdir, join(project_dir, DEFAULTSECTION.get('env_link')))
        static_dir = join(shared_env, 'static')
        if not os.path.exists(static_dir):
            os.makedirs(static_dir, exist_ok=True)

    if dev_repos:
        click.echo("dev_repos is {} --> {}".format(dev_repos, dev_repos.split()))
        repos = []
        for nickname in dev_repos.split():
            lib = REPOS_DICT.get(nickname, None)
            if lib is None:
                raise click.ClickException("Invalid repository nickname {} in --dev-repos".format(nickname))
            repos.append(lib)

        click.echo("Installing {} repositories...".format(len(repos)))
        full_repos_dir = DEFAULTSECTION.get('repos_base')
        if not full_repos_dir:
            full_repos_dir = join(envdir, DEFAULTSECTION.get('repos_link'))
            if not os.path.exists(full_repos_dir):
                os.makedirs(full_repos_dir, exist_ok=True)
        i.check_permissions(full_repos_dir)
        os.chdir(full_repos_dir)
        for lib in repos:
            i.clone_repo(lib)
        for lib in repos:
            i.install_repo(lib, envdir)

    if len(pip_packages):
        click.echo("Installing {} Python packages...".format(len(pip_packages)))
        i.run_in_env(envdir, "pip install --upgrade {}".format(' '.join(pip_packages)))

    if ifroot():
        if USE_NGINX:
            filename = "{}.conf".format(prjname)
            avpth = join(SITES_AVAILABLE, filename)
            enpth = join(SITES_ENABLED, filename)
            # shutil.copyfile(join(project_dir, 'nginx', filename), avpth)
            if i.jinja_write(avpth, "nginx.conf", **context):
                if i.override_batch(True):
                    if i.check_overwrite(enpth):
                        os.symlink(avpth, enpth)
            i.write_supervisor_conf('{}-uwsgi.conf'.format(prjname),
                 UWSGI_SUPERVISOR_CONF.format(**context))
            i.must_restart("supervisor")
            i.must_restart("nginx")
            if DEFAULTSECTION.getboolean('https'):
                i.runcmd("certbot-auto --nginx -d {} -d www.{}".format(server_domain,server_domain))
                i.must_restart("nginx")

    os.chdir(project_dir)
    i.run_in_env(envdir, "python manage.py install --noinput")
    if not shared_user:
        db_engine.setup_user(i, context)
    db_engine.setup_database(i, prjname, db_user, db_host)
    i.run_in_env(envdir, "python manage.py migrate --noinput")
    i.run_in_env(envdir, "python manage.py prep --noinput")
    db_engine.after_prep(i, context)
    if ifroot():
        i.run_in_env(envdir, "python manage.py collectstatic --noinput")

    i.run_apt_install()
    i.restart_services()

    click.echo("The new site {} has been created.".format(prjname))
