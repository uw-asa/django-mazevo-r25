# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/uw-asa/django-mazevo-r25/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                            |    Stmts |     Miss |   Cover |   Missing |
|------------------------------------------------ | -------: | -------: | ------: | --------: |
| mazevo\_r25/\_\_init\_\_.py                     |        4 |        0 |    100% |           |
| mazevo\_r25/admin.py                            |       43 |       28 |     35% |9-30, 43-69 |
| mazevo\_r25/management/\_\_init\_\_.py          |        0 |        0 |    100% |           |
| mazevo\_r25/management/commands/\_\_init\_\_.py |        0 |        0 |    100% |           |
| mazevo\_r25/management/commands/mazevo2r25.py   |      207 |      207 |      0% |     1-438 |
| mazevo\_r25/migrations/0001\_initial.py         |        5 |        0 |    100% |           |
| mazevo\_r25/migrations/0002\_mazevostatusmap.py |        4 |        0 |    100% |           |
| mazevo\_r25/migrations/\_\_init\_\_.py          |        0 |        0 |    100% |           |
| mazevo\_r25/models.py                           |       52 |       20 |     62% |15-18, 22, 30, 34-37, 47-50, 54, 71, 75-78 |
| mazevo\_r25/more\_r25.py                        |      218 |      164 |     25% |18, 55-59, 62, 89-94, 97, 118-137, 141-146, 158-206, 217-239, 255-280, 295-309, 323-333, 350-455, 466-470 |
| mazevo\_r25/tests/\_\_init\_\_.py               |        0 |        0 |    100% |           |
| mazevo\_r25/tests/test\_more\_r25.py            |       19 |        0 |    100% |           |
| mazevo\_r25/utils.py                            |       32 |       32 |      0% |      1-52 |
|                                       **TOTAL** |  **584** |  **451** | **23%** |           |


## Setup coverage badge

Below are examples of the badges you can use in your main branch `README` file.

### Direct image

[![Coverage badge](https://raw.githubusercontent.com/uw-asa/django-mazevo-r25/python-coverage-comment-action-data/badge.svg)](https://htmlpreview.github.io/?https://github.com/uw-asa/django-mazevo-r25/blob/python-coverage-comment-action-data/htmlcov/index.html)

This is the one to use if your repository is private or if you don't want to customize anything.

### [Shields.io](https://shields.io) Json Endpoint

[![Coverage badge](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/uw-asa/django-mazevo-r25/python-coverage-comment-action-data/endpoint.json)](https://htmlpreview.github.io/?https://github.com/uw-asa/django-mazevo-r25/blob/python-coverage-comment-action-data/htmlcov/index.html)

Using this one will allow you to [customize](https://shields.io/endpoint) the look of your badge.
It won't work with private repositories. It won't be refreshed more than once per five minutes.

### [Shields.io](https://shields.io) Dynamic Badge

[![Coverage badge](https://img.shields.io/badge/dynamic/json?color=brightgreen&label=coverage&query=%24.message&url=https%3A%2F%2Fraw.githubusercontent.com%2Fuw-asa%2Fdjango-mazevo-r25%2Fpython-coverage-comment-action-data%2Fendpoint.json)](https://htmlpreview.github.io/?https://github.com/uw-asa/django-mazevo-r25/blob/python-coverage-comment-action-data/htmlcov/index.html)

This one will always be the same color. It won't work for private repos. I'm not even sure why we included it.

## What is that?

This branch is part of the
[python-coverage-comment-action](https://github.com/marketplace/actions/python-coverage-comment)
GitHub Action. All the files in this branch are automatically generated and may be
overwritten at any moment.