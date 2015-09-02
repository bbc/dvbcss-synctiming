# Release process for dvbcss-synctiming

## Explanation of the process sequence

Assumption that the current state of *master* will constitute the release...

#### 1. Pre-release checks

Make the following checks before performing a release:
   * Do all unit tests pass?
   * Do all programs/tools work?
   * Has the documentation been updated?

Check this for all parts (e.g. dont' forget the test sequence generator)


#### 2. Decide the version number
   
The structure is: *major* **.** *minor* **.** *revision*.
The *revision* part is *not included* if it is zero '0' (just after a *major* or *minor* increment).
   * *major* = significant incompatible change (e.g. partial or whole rewrite).
   * *minor* = some new functionality or changes that are mostly/wholly backward compatible.
   * *revision* = very minor changes, e.g. bugfixes.

#### 3. Update CHANGELOG

The is in the [`CHANGELOG.md`](CHANGELOG.md) file. Ensure it mentions any noteworthy changes since the previous release.


#### 4. Create release branch 

Create the branch, naming it after the release version number (just the number).


#### 5. Create a new release on GitHub based on the new branch

Put a shorter summary of the new changelog items into the release notes.
Make the tag name the version number (the same as the branch name).

- - - - -

## Example of release process sequence

This example assumes your local repository is a clone and the working copy is currently at the head of the master branch, and that this is all 
synced with GitHub. 

    $ git status
    On branch master
    Your branch is up-to-date with 'origin/master'.
    nothing to commit, working directory clean
    
#### 1. Run checks

Run unit tests:

    $ python tests/test_all.py
    $ cd test_sequence_gen
    $ python tests/test_all.py
    $ cd ..
    
And run all the tools, including the test sequence generator, to check they work!


#### 2. Decide the version number

The remainder of this example sequence will assume we have decided to do a release "X.Y.Z"


#### 3. Update CHANGELOG

Modify `CHANGELOG.md` e.g. using `vi`:

    $ vi CHANGELOG.md
        .. update change log  ..
    $ git add CHANGELOG.md
    $ git commit -m "Changelog update ready for release"
    $ git push origin master

#### 4. Create release branch

Create new branch (locally):

    $ git checkout -b 'X.Y.Z'

Update CHANGELOG.md to remove "latest" heading. Then commit.

    $ git commit -m "Release branch"

Finally branch up to github (and set local repository to track upstream branch on origin):

    $ git push -u origin 'X.Y.Z'
    

#### 6. Create a new release on GitHub based on the new branch

Now use the [new release](https://github.com/bbc/pydvbcss/releases/new) function on GitHub's web interface to
mark the branch 'X.Y.Z' as a new release.
