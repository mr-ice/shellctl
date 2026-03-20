# env-config
env-config is to be a tool to allow the operator to control their shell environment startup files

## Features


1. Figure out the user's preferred shell, and if it is different from their current loginShell (via getpwent), we'll have a process to help them change it.   The preferred shell could be chosen in any of these ways:
   1. by providing a shell or shell family name on the commandline
   2. by setting the SHELL environment variable
   3. by running the tool from a shell other than their loginShell
 
2. Provide a way to find all shell startup files in a home directory that are sourced by any of the shell families (bash, tcsh, and zsh).  Use techniques to find the actual files sourced in all combinations of 'login' and 'interactive' modes.  Do not assume files not present or not sourced by the shell, and we need to find the ones that are sourced by the shell (e.g. when they are sourced in other files)
   1. bash doesn't print the filenames with -x, we need to create a patched version to do this.
   2. tcsh doesn't allow '-l' with other options and does not print the filenames with -x, we need to create a patched version to do this.
   3. zsh already does this
   4. keep instructions and urls to rebuild the patched shells so that we can deploy them with this tool.
   5. When generating the list, be able to show which are sourced in which modes.

3. Establish a global and user-level configuration file for configuration elements for this env-config tool.  Establish the elements that need to be there, and provide a command-line and TUI way to edit these elements storing operator specific ones in the operator's home directory.

3. This script should work cleanly in three modes.
   1. Non-Interactive to complete a task without prompting from the operator.
   2. Interactive when the operator gives partial commands or no commands.
   3. TUI when selected by the operator will take all the same commandline parameters but will open a TUI view of things.

4. A default mode is to show the shell startup files, first for the current shell, then for the intended shell, then for any shells that aren't the intended or current shell.  In TUI mode, some action buttons should be immediately available for the rest of the actions.

5. Backup or Archive mode should allow the operator to select or deselect shell startup files to include in a backup (location configurable).  Archive removes the files after backing them up.  Backups should be pruned regularly, keeping only the most recent but configurable to keep more.

6. List of backups should be requestable, selectable in interactive and tui modes, and upon selection will be restored responsibly.  Prompt to Make an archive of existing files that would be overwritten by the restore if they are different from those restored.  If the restore would not overwrite any files with differences do not prompt for archival.
   1. In TUI mode when a backup is selected show the files that would be restored and overwritten in a file-browser like view which is the sameas used in step 4.

7. A url in the repo will be used to clone a project that will have initial startup files.  Ensure a checked out copy of this is up to date with a branch named in the configuration on startup. It is an error if the location is not a clone of the repo, but only a warning if it is not on the intended branch or not up to date (offer the operator a chance to fix it)
   
8.  Have controls to `init` the shell environment for the user to the intended shell.  This will `archive` the files in the user's directory if they are not currently archived and would be overwritten, then copy files from the repo based on the shell family into the user's home directory.

9.  Have controls to `compose` by picking additional optional shell initialization files from a path in the configuration.  These will be shown in a file picker in interactive and tui mode, or can be listed and selected by matching a commandline argument in non-interactive mode.  The first line of these files should be a description in a comment, followed by a longer description in comments.  Show the first line of the description comment beside the filename in lists for the user to search or select.
    
    1. Driectories in the path must be a main:HEAD directory of a repo with a '*.sarc.samsung.com' URL or the should be ignored with a warning.
    2. These files must have a filename matching {shell}{part}-{tag} where {shell}{part} matches one of the shells' startup paths.  And -{tag} makes it unique.  These are copied verbatim into the operator's home directory with a leading '.'.
    3. Keep a registry in the user's config file of all these that were selected by the user.
    4. Keep these up-to-date either by symlinking, redownloading, or recopying the files while running the script in interactive or tui mode.
    5. Create and follow a guideline of how to pull the composed parts into the user's home directory (from ['link','copy','clone'])
    6. Warn if a file is selected by the parent file (~/.{shell}{part} like ~/.zprofile) does not have a stanza to read these in (all the files in the repo should have this).  For example:
```
for _rc in $HOME/.zshenv-*; do
    source $_rc
done
```

10.  Have controls to `update` all elements that came from `init` or `compose` to be compared to their source and re-updated if they are found to be out of date.

Make sure each feature works and has good tests before integrating it into the operator endpoint scripts and TUI.