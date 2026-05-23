package wildberries

func calculatePages(limit int, pageSize int) int {
	if limit <= 0 {
		return 1
	}

	pages := limit / pageSize
	if limit%pageSize != 0 {
		pages++
	}

	if pages == 0 {
		return 1
	}

	return pages
}
