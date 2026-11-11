# GitHub migration

## Source repository

Initialize a new repository from this extracted source package:

```sh
git init -b main
git add .
git commit -m "Initial source release"
git remote add origin https://github.com/OWNER/REPOSITORY.git
git push -u origin main
```

The package contains the frontend, server, tests, schemas, and demo fixtures.
Set the Code button and repository links to the new GitHub URL.

## Website

The runnable demo is in `dist/`. Publish that directory with GitHub Pages or
another static host. URL paths are relative, including project sites served
under `/REPOSITORY/`. The `.nojekyll` file selects static-file serving.

For the experiment showcase, supply the results JSON, catalog, episode
registrations, and media described in `DATA_CONTRACTS.md`. Keep the source
repository small; host the full frame archive and video collection separately
when assembling the project site.

GitHub Pages has a 1 GB published-site limit and does not serve Git LFS media.
For normal Git, individual files must be below 100 MiB and a push below 2 GiB.

References: [Pages limits](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits),
[large files](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github),
[Git LFS](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-git-large-file-storage),
[push limit](https://docs.github.com/en/get-started/using-git/troubleshooting-the-2-gb-push-limit).
