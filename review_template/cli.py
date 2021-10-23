import datetime
import os
import sys

import click
import git


class SpecialHelpOrder(click.Group):

    def __init__(self, *args, **kwargs):
        self.help_priorities = {}
        super().__init__(*args, **kwargs)

    def get_help(self, ctx):
        self.list_commands = self.list_commands_for_help
        return super().get_help(ctx)

    def list_commands_for_help(self, ctx):
        """reorder the list of commands when listing the help"""
        commands = super().list_commands(ctx)
        return (c[1] for c in sorted(
            (self.help_priorities.get(command, 1), command)
            for command in commands))

    def command(self, *args, **kwargs):
        """Behaves the same as `click.Group.command()` except capture
        a priority for listing command names in help.
        """
        help_priority = kwargs.pop('help_priority', 1)
        help_priorities = self.help_priorities

        def decorator(f):
            cmd = super(SpecialHelpOrder, self).command(*args, **kwargs)(f)
            help_priorities[cmd.name] = help_priority
            return cmd

        return decorator

# Note: autocompletion needs bash/... activation:
# https://click.palletsprojects.com/en/7.x/bashcomplete/


@click.group(cls=SpecialHelpOrder)
@click.pass_context
def main(ctx):
    """Review template pipeline

    Main commands: init | status | process, screen, ..."""


@main.command(help_priority=1)
@click.pass_context
def init(ctx):
    """Initialize repository"""
    from review_template import init
    init.initialize_repo()


@main.command(help_priority=2)
@click.pass_context
def status(ctx):
    """Show status"""
    from review_template import status
    status.repository_validation()
    print('\nChecks\n')
    os.system('pre-commit run -a')
    status.main()


@main.command(help_priority=3)
@click.pass_context
@click.option('--reprocess',
              help='Entry ID to reprocess ("all" to reprocess all).')
def process(ctx, reprocess):
    """Process pipeline"""
    from review_template import process
    process.main(reprocess)


@main.command(help_priority=5)
@click.pass_context
def man_prep(ctx):
    """Prepare records manually"""
    from review_template import prepare_manual
    prepare_manual.main()


@main.command(help_priority=6)
@click.pass_context
def man_dedupe(ctx):
    """Process duplicates manually"""
    from review_template import man_dedupe
    man_dedupe.main()


@main.command(help_priority=7)
@click.pass_context
def prescreen(ctx):
    """Execute pre-screen"""
    from review_template import screen
    screen.prescreen()


@main.command(help_priority=8)
@click.pass_context
def screen(ctx):
    """Execute screen"""
    from review_template import screen
    screen.screen()


@main.command(help_priority=9)
@click.pass_context
def pdfs(ctx):
    """Acquire PDFs"""
    from review_template import pdfs
    pdfs.main()


@main.command(help_priority=10)
@click.pass_context
def pdf_check(ctx):
    """Check PDFs"""
    from review_template import pdf_check
    pdf_check.main()


@main.command(help_priority=11)
@click.pass_context
def back_search(ctx):
    """Execute backward search based on PDFs"""
    from review_template import back_search
    back_search.main()


@main.command(help_priority=12)
@click.pass_context
def data(ctx):
    """Execute data extraction"""
    from review_template import data
    data.main()


@main.command(help_priority=13)
@click.pass_context
def profile(ctx):
    """Generate a sample profile"""
    from review_template import profile
    profile.main()


def validate_commit(ctx, param, value):
    if 'none' == value:
        return value
    repo = git.Repo()

    revlist = [commit for commit in repo.iter_commits()]

    if value in [x.hexsha for x in revlist]:
        # TODO: allow short commit_ids as values!
        return value
    else:
        print('Error: Invalid value for \'--commit\': not a git commit id\n')
        print('Select any of the following commit ids:')
        commits_for_checking = []
        for c in reversed(list(revlist)):
            commits_for_checking.append(c)
        for commit in revlist:
            print(commit.hexsha,
                  datetime.datetime.fromtimestamp(commit.committed_date),
                  ' - ', commit.message.replace('\n', ' '))
        print('\n')
        raise click.BadParameter('not a git commit id')


@main.command(help_priority=14)
@click.option('--scope',
              type=click.Choice(['prepare', 'merge', 'all'],
                                case_sensitive=False),
              default='all', help='prepare, merge, or all.')
@click.option('--commit', help='Git commit id to validate.',
              default='none', callback=validate_commit)
@click.pass_context
def validate(ctx, scope, commit):
    """Validate changes"""
    from review_template import validate
    validate.main(scope, commit)


@main.command(help_priority=16)
@click.pass_context
@click.option('--id', help='Entry ID to trace (citation_key).', required=True)
def trace(ctx, id):
    """Trace an entry"""
    from review_template import trace
    trace.main(id)


@main.command(help_priority=17)
@click.pass_context
def paper(ctx):
    """Build the paper from markdown"""
    from review_template import paper
    paper.main()


if __name__ == '__main__':
    sys.exit(main())
