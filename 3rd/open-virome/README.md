# Open Virome

- [Open Virome Online](https://openvirome.com)
- [OpenViromeR](https://github.com/ababaian/open.viromeR): `R` language interface package for Open Virome data

## Starting an Open Virome instance locally

To start the app using local frontend with API calls to the remote server

```sh
cd frontend
npm install
npm start
```

To start the app using local front end and local API:

```
cd frontend
npm install
npm run start-local
```

In a second terminal

```
cd api
npm install
npm start
```

## Running MWAS locally

You will need a local installation of s5cmd to display MWAS data when running the API locally. Can be installed with [pip](https://pypi.org/project/s5cmd/) or [binaries](https://github.com/peak/s5cmd?tab=readme-ov-file#installation).

This is because we are temporarilly using precomputed MWAS values from s3. We'll likely update this to either use a database to store precomputed results or compute on demand with a lambda API.
