# Profile README operations

This folder is for maintaining `marufhossen-in/marufhossen-in`; it is not part of the public-facing profile text.

## Repository target

Create or update the **public** repository named exactly `marufhossen-in/marufhossen-in`, then copy this package's `README.md`, `assets/`, `.github/`, `scripts/`, and `docs/` into its default branch.

## Activity and statistics pipeline

### What is generated

`.github/workflows/update-profile-assets.yml` runs the Python standard-library script `scripts/update_profile_assets.py` once a day and on manual dispatch. It writes three static, repository-hosted SVGs:

- `assets/contributions.svg` — GitHub's last-year contribution calendar, with per-day counts and an anonymized heatmap.
- `assets/profile-stats.svg` — public repository count, followers, stars on original public repositories, last-year contributions, current streak, and best streak within the last year.
- `assets/languages.svg` — the top languages by byte count, aggregated from the GitHub language endpoint across public, non-fork repositories.

The script does not store repository names, code, private source, email addresses, or tokens in the generated SVGs. The contribution image contains only dates, contribution counts, and color levels.

### One-time GitHub setup

1. In GitHub, create a **classic personal access token** with only the `read:user` scope. The token is for reading contribution-calendar information; do not add repository write access.
2. In `marufhossen-in/marufhossen-in`, open **Settings → Secrets and variables → Actions → New repository secret**. Name it `PROFILE_TOKEN` and paste the token value.
3. Open **Settings → Actions → General → Workflow permissions** and allow read/write permissions for the repository's `GITHUB_TOKEN`. The workflow limits that token to `contents: write` and uses it only to commit updated SVGs.
4. Go to **Actions → Refresh profile activity assets → Run workflow**. After the run completes, confirm that the three SVGs are present and that the README previews them.
5. If private contribution counts should appear, enable GitHub's **Include private contributions on my profile** setting. The graph displays only daily aggregate counts, never repository names.

The `PROFILE_TOKEN` is sent only to GitHub's API during the Action run. It is never printed, committed, embedded in the README, or written into an SVG. If the secret is missing or expires, the Action fails without replacing the previous committed images; the profile still displays its last successful snapshot.

### Freshness and fallback

- The schedule is daily at **04:25 UTC**. GitHub may delay scheduled workflows, and GitHub's raw-file CDN may cache committed assets briefly.
- The current committed snapshot was initialized from Maruf's public GitHub profile calendar and public REST data on **2026-10-05**. The scheduled workflow switches subsequent updates to GitHub's official GraphQL API.
- The dependable fallback is the native profile at [github.com/marufhossen-in](https://github.com/marufhossen-in), where GitHub always displays its own contribution calendar.
- If the images ever need a manual refresh, run the workflow with `workflow_dispatch`; no separate card-hosting account is required.

### Reliability decisions

- **Contribution heatmap — selected: GitHub GraphQL + GitHub Actions + committed SVG.** GitHub's `contributionsCollection.contributionCalendar` is the source. The GraphQL reference documents contribution calendars and notes that private/internal contribution counts are available with the optional `read:user` scope. The image is generated in this repo, so page views do not call a shared image server. Fallback: the native GitHub profile calendar. Optional: the custom visual is optional; the native profile remains available either way.
- **Profile stats and language mix — selected: GitHub REST API + GitHub Actions + committed SVG.** Public profile/repository data are aggregated once per scheduled run. The stats are a snapshot until the next successful run, not a live request on each README view. Fallback: the public GitHub profile and repository list. Optional: remove the two image tags from the README if you prefer a text-only profile.
- **Streak — selected: local calculation from the same contribution calendar.** This avoids a separate hosted streak image. `Best streak` is explicitly limited to the last 12-month calendar returned by GitHub; it is not presented as an all-time record. Fallback: omit the two streak tiles in the generator and keep the contribution heatmap.
- **Visitor counter — omitted.** It adds low-signal traffic, another external service, and does not help communicate engineering work.
- **Third-party live cards — not selected.** A direct check on **2026-10-05** returned HTTP 402 (`DEPLOYMENT_DISABLED`) from `github-readme-activity-graph.vercel.app`; the upstream also has a recent outage report. At that same check, the legacy stats endpoint, GitHub Stats Extended, and `streak-stats.demolab.com` returned HTTP 200. The legacy `github-readme-stats` repository nevertheless says it is no longer maintained, points users to GitHub Stats Extended, and warns that its shared Vercel instance is best-effort and can be rate-limited. Stats Extended is active and was responding when checked, but using it would still make every profile render depend on a third-party image host. Since this profile can generate the same small visuals from GitHub's official APIs once per day, the implementation keeps those assets in the profile repository instead.

Useful references:

- [GitHub GraphQL Users reference: contribution calendars and contribution collections](https://docs.github.com/en/graphql/reference/users)
- [GitHub REST Users reference](https://docs.github.com/en/rest/users/users)
- [GitHub REST Repositories reference](https://docs.github.com/en/rest/repos/repos)
- [Activity Graph Vercel outage report](https://github.com/Ashutosh00710/github-readme-activity-graph/issues/264)
- [Activity Graph discussion of generated/self-hosted assets](https://github.com/Ashutosh00710/github-readme-activity-graph/issues/265)
- [GitHub Readme Stats maintenance notice and reliability guidance](https://github.com/anuraghazra/github-readme-stats)
- [GitHub Stats Extended successor project](https://github.com/stats-organization/github-stats-extended)

## Updating project screenshots

The four `assets/project-*.jpg` files are compressed captures of the real live demo pages, captured on **2026-10-05**. They are static local assets, so a README view makes no screenshot-service request. Refresh a JPG manually when its live site changes; never replace it with a synthetic mock of the actual project.

## Later profile edits

- Add a WhatsApp link only when Maruf provides the real number or URL; the README currently keeps a non-clickable, clearly labelled slot.
- Change the short bio and `Currently building` bullets to match current work; avoid describing an exploration as a launched product.
- Update stack claims from the relevant repository's `package.json`/README rather than assuming every project uses the same libraries.
- Keep project screenshots and URLs matched to their real deployments. Source links in the current README were cross-checked against Maruf's public GitHub repositories.
- Re-run the quality audit after changing local image paths or workflow output names.
