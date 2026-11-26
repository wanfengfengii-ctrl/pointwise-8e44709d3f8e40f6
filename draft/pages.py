def validate_page_number(page):
    if type(page) is not int or page <= 0:
        raise ValueError('页号必须是正整数。')
    return page


def normalize_allowed_pages(pages):
    try:
        source = iter(pages)
    except TypeError as error:
        raise ValueError('每段引文都需要允许页格。') from error
    normalized = tuple(sorted({validate_page_number(page) for page in source}))
    if not normalized:
        raise ValueError('每段引文至少需要一个允许页格。')
    return normalized
