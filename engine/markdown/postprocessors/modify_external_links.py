from bs4 import BeautifulSoup


def modify_external_links(html, context):  # ← Must accept both parameters
    """
    Add target="_blank" and rel="noopener" to external links
    This runs AFTER markdown conversion
    """
    soup = BeautifulSoup(html, "html.parser")

    for link in soup.find_all("a", href=True):
        href = link["href"]

        # Check if external link
        if href.startswith(("http://", "https://")) and not href.startswith(
            "https://yourdomain.com"
        ):
            link["target"] = "_blank"
            link["rel"] = "noopener noreferrer"

            # Optionally add icon class
            if "class" in link.attrs:
                link["class"].append("external-link")
            else:
                link["class"] = ["external-link"]

    return str(soup)
