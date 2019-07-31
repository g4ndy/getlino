# Copyright 2019 Rumma & Ko Ltd
# License: BSD (see file COPYING for details)

import os
import shutil
import virtualenv
import click

from os.path import join
from cookiecutter.main import cookiecutter

from .utils import APPNAMES, FOUND_CONFIG_FILES, DEFAULTSECTION, USE_NGINX
from .utils import DB_ENGINES, BATCH_HELP, REPOS_DICT, KNOWN_REPOS
from .utils import Installer, check_usergroup

SITES_AVAILABLE = '/etc/nginx/sites-available'
SITES_ENABLED = '/etc/nginx/sites-enabled'

COOKIECUTTER_URL = "https://github.com/lino-framework/cookiecutter-startsite"

# note that we double curly braces because we will run format() on this string:
LOGROTATE_CONF = """
{log_root}/{prjname}/lino.log {{
        weekly
        missingok
        rotate 156
        compress
        delaycompress
        notifempty
        create 660 root www-data
        su root www-data
        sharedscripts
}}

"""

UWSGI_SUPERVISOR_CONF = """
# generated by getlino
[program:{prjname}-uwsgi]
command = /usr/bin/uwsgi --ini {project_dir}/nginx/{prjname}_uwsgi.ini
user = {usergroup}
umask = 0002
"""



@click.command()
@click.argument('appname', metavar="APPNAME", type=click.Choice(APPNAMES))
@click.argument('prjname')
@click.option('--batch/--no-batch', default=False, help=BATCH_HELP)
@click.option('--dev-repos', default='',
              help="List of packages for which to install development version")
@click.pass_context
def startsite(ctx, appname, prjname, batch, dev_repos):
    """
    Create a new Lino site.

    Arguments:

    APPNAME : The application to run on the new site.

    SITENAME : The name for the new site.

    """ # .format(appnames=' '.join(APPNAMES))

    # if len(FOUND_CONFIG_FILES) == 0:
    #     raise click.UsageError(
    #         "This server is not yet configured. Did you run `sudo -H getlino configure`?")

    i = Installer(batch)

    # if os.path.exists(prjpath):
    #     raise click.UsageError("Project directory {} already exists.".format(prjpath))

    # prod = DEFAULTSECTION.getboolean('prod')
    projects_root = DEFAULTSECTION.get('projects_root')
    local_prefix = DEFAULTSECTION.get('local_prefix')
    python_path_root = join(projects_root, local_prefix)
    project_dir = join(python_path_root, prjname)
    shared_env = DEFAULTSECTION.get('shared_env')
    admin_name = DEFAULTSECTION.get('admin_name')
    admin_email = DEFAULTSECTION.get('admin_email')
    server_domain = prjname + "." + DEFAULTSECTION.get('server_domain')
    server_url = ("https://" if DEFAULTSECTION.getboolean('https') else "http://") \
                 + server_domain
    db_user = prjname
    db_password = "1234"  # todo: generate random password
    db_engine = DEFAULTSECTION.get('db_engine')
    db_port = DEFAULTSECTION.get('db_port')

    app = REPOS_DICT.get(appname, None)
    if app is None:
        raise click.ClickException("Invalid application nickname {}".format(appname))

    if not app.settings_module:
        raise click.ClickException("{} is a library, not an application".format(appname))

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

    usergroup = DEFAULTSECTION.get('usergroup')

    if check_usergroup(usergroup) or True:
        click.echo("OK you belong to the {0} user group.".format(usergroup))
    else:
        msg = """\
ERROR: you don't belong to the {0} user group.  Maybe you want to run:
sudo adduser `whoami` {0}"""
        raise click.ClickException(msg.format(usergroup))

    app_package = app.package_name
    # app_package = app.settings_module.split('.')[0]
    repo_nickname = app.git_repo.split('/')[-1]

    context = {}
    context.update(DEFAULTSECTION)
    pip_packages = []
    if app.nickname not in dev_repos:
        pip_packages.append(app.package_name)
    for nickname in ("lino", "xl"):
        if nickname not in dev_repos:
            pip_packages.append(REPOS_DICT[nickname].package_name)
    context.update({
        "prjname": prjname,
        "appname": appname,
        "project_dir": project_dir,
        "repo_nickname": repo_nickname,
        "app_package": app_package,
        "app_settings_module": app.settings_module,
        "django_settings_module": "{}.{}.settings".format(local_prefix, prjname),
        "server_domain":server_domain,
        "dev_packages": ' '.join([a.nickname for a in KNOWN_REPOS if a.nickname in dev_repos]),
        "pip_packages": ' '.join(pip_packages),
        # "use_app_dev": app.nickname in dev_repos,
        # "use_lino_dev": linodev,
        "server_url": server_url,
        "db_name": prjname,
        "python_path": projects_root,
        "usergroup": usergroup
    })

    click.echo(
        'Create a new Lino {appname} site into {project_dir}'.format(
            **context))

    if not batch:
        shared_env = click.prompt("Shared virtualenv", default=shared_env)
        # if asroot:
        #     server_url = click.prompt("Server URL ", default=server_url)
        #     admin_name = click.prompt("Administrator's full name", default=admin_name)
        #     admin_email = click.prompt("Administrator's full name", default=admin_email)
        if db_engine != "sqlite3":

            click.echo(
                "Database settings (for {db_engine} on {db_host}:{db_port}):".format(
                    **context))
            db_user = click.prompt("- user name", default=db_user)
            db_password = click.prompt("- user password", default=db_password)
            # db_port = click.prompt("- port", default=db_port)
            # db_host = click.prompt("- host name", default=db_host)

    if not i.yes_or_no("OK to create {} with above options ? [y or n]".format(project_dir)):
        raise click.Abort()

    context.update({
        "db_user": db_user,
        "db_password": db_password,
    })

    os.umask(0o002)

    # click.echo("cookiecutter context is {}...".format(extra_context))
    click.echo("Running cookiecutter {}...".format(COOKIECUTTER_URL))
    cookiecutter(
        COOKIECUTTER_URL,
        no_input=True, extra_context=context, output_dir=python_path_root)

    if i.asroot:
        logdir = join(DEFAULTSECTION.get("log_root"), prjname)
        os.makedirs(logdir, exist_ok=True)
        with i.override_batch(True):
            i.check_permissions(logdir)
            os.symlink(logdir, join(project_dir, 'log'))

            # add cron logrotate entry
            i.write_file(
                '/etc/logrotate.d/lino-{}.conf'.format(prjname),
                LOGROTATE_CONF.format(**context))

    os.makedirs(join(project_dir, 'media'), exist_ok=True)

    is_new_env = True
    if shared_env:
        envdir = shared_env
        if os.path.exists(envdir):
            is_new_env = False
            venv_msg = "Update shared virtualenv in {}"
        else:
            venv_msg = "Create shared virtualenv in {}"
    else:
        envdir = join(project_dir, DEFAULTSECTION.get('env_link'))
        venv_msg = "Create local virtualenv in {}"

    if is_new_env:
        if batch or click.confirm(venv_msg.format(envdir), default=True):
            virtualenv.create_environment(envdir)

    if shared_env:
        os.symlink(envdir, join(project_dir, DEFAULTSECTION.get('env_link')))
        static_dir = join(shared_env, 'static')
        if not os.path.exists(static_dir):
            os.makedirs(static_dir, exist_ok=True)

    full_repos_dir = DEFAULTSECTION.get('repositories_root')
    if not full_repos_dir:
        full_repos_dir = join(envdir, DEFAULTSECTION.get('repos_link'))
        if not os.path.exists(full_repos_dir):
            os.makedirs(full_repos_dir, exist_ok=True)
            i.check_permissions(full_repos_dir)

    click.echo("Installing repositories ...".format(full_repos_dir))
    if dev_repos:
        os.chdir(full_repos_dir)
        for nickname in dev_repos.split():
            lib = REPOS_DICT.get(nickname, None)
            if lib is None:
                raise click.ClickException("Invalid repo nickname {}".format(nickname))
            i.install_repo(lib)

    for pkgname in pip_packages:
        i.run_in_env(envdir, "pip install {}".format(pkgname))

    for e in DB_ENGINES:
        if DEFAULTSECTION.get('db_engine') == e.name:
            i.run_in_env(envdir, "pip install {}".format(e.python_packages))

    if i.asroot:
        if USE_NGINX:

            if batch or click.confirm("Configure nginx", default=True):
                filename = "{}.conf".format(prjname)
                avpth = join(SITES_AVAILABLE, filename)
                enpth = join(SITES_ENABLED, filename)
                with i.override_batch(True):
                    if i.check_overwrite(avpth):
                        shutil.copyfile(join(project_dir, 'nginx', filename), avpth)
                    if i.check_overwrite(enpth):
                        os.symlink(avpth, enpth)
                    i.must_restart("nginx")
                    i.write_supervisor_conf('{}-uwsgi.conf'.format(prjname),
                         UWSGI_SUPERVISOR_CONF.format(**context))
                if DEFAULTSECTION.getboolean('https'):
                    i.runcmd("certbot-auto --nginx -d {} -d www.{}".format(server_domain,server_domain))
                    i.must_restart("nginx")

    os.chdir(project_dir)
    i.run_in_env(envdir, "python manage.py configure")
    i.setup_database(prjname, db_user, db_password, db_engine)
    i.run_in_env(envdir, "python manage.py prep --noinput")

    if i.asroot:
        i.run_in_env(envdir, "python manage.py collectstatic --noinput")

    i.finish()
