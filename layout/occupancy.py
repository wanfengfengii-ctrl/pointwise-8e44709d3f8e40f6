class Occupancy:
    def __init__(self):
        self._by_page = {}
        self._by_quote = {}
        self._fixed = set()

    def reserve(self, quote, page):
        if quote in self._by_quote or page in self._by_page:
            raise ValueError('固定页与现有占用冲突。')
        self.reassign(quote, page)
        self._fixed.add(quote)

    def occupant(self, page):
        return self._by_page.get(page)

    def reassign(self, quote, page):
        if quote in self._fixed or page in self._by_page:
            raise ValueError('改派目标必须空闲，且引文不能处于固定页。')
        former = self._by_quote.get(quote)
        if former is not None:
            del self._by_page[former]
        self._by_quote[quote] = page
        self._by_page[page] = quote
        return former

    def assignments(self):
        return tuple(sorted(self._by_quote.items()))
