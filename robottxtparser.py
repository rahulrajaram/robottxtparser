"""
Program processes a robot.txt file to verify that it is legal according to the grammar:

```
 robotstxt = *(group / emptyline)
 group = *(startgroupline / emptyline) ; ... and possibly more
                                       ; user-agent lines
        *(rule / emptyline)            ; followed by rules relevant
                                       ; for the preceding
                                       ; user-agent lines

 startgroupline = *WS "user-agent" *WS ":" *WS product-token EOL

 nonstandard-field = "crawl-delay"

 nonstandard-rule = *WS nonstandard-field *WS ":" *WS value EOL

 rule = *WS ("allow" / "disallow") *WS ":"
       *WS (path-pattern / empty-pattern) EOL

 ; parser implementors: define additional lines you need (for
 ; example, Sitemaps).

sitemap-rule = *WS "sitemap" *WS ":" *WS URI EOL

 product-token = identifier 1"*" / "*"
 path-pattern = "/" *UTF8-char-noctl ; valid URI path pattern
 empty-pattern = *WS

 identifier = 1*(%x2D / %x30-39 / %x41-5A / %x5F / %x61-7A)
 comment = "#" *(UTF8-char-noctl / WS / "#")
 emptyline = EOL
 EOL = *WS [comment] NL ; end-of-line may have
                        ; optional trailing comment
 NL = %x0D / %x0A / %x0D.0A
 WS = %x20 / %x09
```

This deviates from [RFC9309](https://datatracker.ietf.org/doc/html/rfc9309) slightly in that
it:

1. allows "*" after identifiers, such as in the production:
2. allows for either an emptyline or a straightgroupline as the first expression within a group;
the RFC expects the first line to be a group
3. allows digits in identifiers for user-agent names
4. supports crawl-delay with floating point values
5. supports Sitemaps nominally
"""
import os
import re

import argparse


def is_WS(token):
    return token in [' ', '\t']


def is_EOL(line):
    tokens = [token.strip() for token in line.strip()]
    i = 0
    while i < len(tokens):
        if tokens[i].startswith('#'):
            return True
        if not is_WS(tokens[i]):
            return False
        i += 1
    return True


def is_emptyline(line):
    return is_EOL(line)


def is_identifier(token):
    identifier_regex = re.compile(r'^[-a-zA-Z0-9_ ./\\]+[\*]?$')
    mtch = identifier_regex.match(token)
    return mtch and mtch.group()


def is_product_token(token):
    """
    product-token = identifier 1 "*" / "*"
    """
    return token == '*' or is_identifier(token)


def is_path_pattern(token):
    """
    Returns True if token conforms to:
    path-pattern = "/" *UTF8-char-noctl
    Where UTF8-char-noctl excludes control characters (0x00–0x1F, 0x7F).
    """
    if not token.startswith('/') and not token.startswith('*/'):
        return False
    try:
        token.encode('utf-8')
    except UnicodeEncodeError:
        return False
    for c in token[1:]:
        o = ord(c)
        if o < 0x20 or o == 0x7F:
            return False
    return True


def is_rule(line):
    """
    Handle

    ```
    rule = *WS ("allow" / "disallow") *WS ":" *WS (path-pattern / empty-pattern) EOL
    ```
    """
    tokens = [token.strip() for token in line.split()]
    i = 0
    # *WS
    while i < len(tokens):
        if not is_WS(tokens[i]):
            break
        i += 1

    # ("allow" / "disallow") *WS ":" 
    if i < len(tokens) and tokens[i].lower() in ['allow', 'disallow']:    
        i += 1
        while i < len(tokens):
            if not is_WS(tokens[i]):
                break
            i += 1
        if i == len(tokens) or not tokens[i] != ":":
            return False
        i += 1
    elif i < len(tokens) and tokens[i].lower() in ['allow:', 'disallow:']:
        i += 1
    else:
        return False
    
    # *WS
    while i < len(tokens):
        if not is_WS(tokens[i]):
            break
        i += 1

    # (path-pattern / empty-pattern) EOL
    if i < len(tokens) and is_path_pattern(tokens[i]):
        i += 1
    else:
        while i < len(tokens):
            if not is_WS(tokens[i]):
                break
            i += 1
    return i == len(tokens)


def is_startgroupline(line):
    """
    Handle

    ```
    startgroupline = *WS "user-agent" *WS ":" *WS product-token EOL
    ```
    """
    tokens = [token.strip() for token in line.split() if token.strip()]
    i = 0

    # *WS
    while i < len(tokens):
        if not is_WS(tokens[i]):
            break
        i += 1

    # "user-agent" *WS ":"
    if i < len(tokens) and tokens[i].lower() == 'user-agent':
        i += 1
        while i < len(tokens):
            if not is_WS(tokens[i]):
                break
            i += 1
        if i == len(tokens) or not tokens[i] != ':':
            return False
    elif i < len(tokens) and tokens[i].lower() == 'user-agent:':
        i += 1
    else:
        return False

    # *WS
    while i < len(tokens):
        if not is_WS(tokens[i]):
            break
        i += 1

    # product-token EOL
    if i == len(tokens):
        raise ValueError(
            f"Expected identifier but found EOL at {line}."
        )

    while i < len(tokens):
        if not is_product_token(tokens[i]):
            raise ValueError(
                f"Expected identifier but found {tokens[i]}. "
                "Identifiers follow the regex r'^[-a-zA-Z0-9_]+[\\*]{1}$'"
            )
        i += 1

    return i == len(tokens)


def is_nonstandard_rule(line):
    tokens = [token.strip() for token in line.split() if token.strip()]
    i = 0

    # *WS
    while i < len(tokens):
        if not is_WS(tokens[i]):
            break
        i += 1

    # "crawl-delay" *WS ":"
    if i < len(tokens) and tokens[i].lower() in [
        "crawl-delay"
    ]:
        i += 1
        while i < len(tokens):
            if not is_WS(tokens[i]):
                break
            i += 1
        if i == len(tokens) or not tokens[i] != ':':
            return False
    elif i < len(tokens) and tokens[i].lower() in [
        "crawl-delay:"
    ]:
        i += 1
    else:
        return False

    # *WS
    while i < len(tokens):
        if not is_WS(tokens[i]):
            break
        i += 1

    # product-token EOL
    if i < len(tokens):
        try:
            float(tokens[i])
        except ValueError:
            raise ValueError(
                f"Expected floating-point value but found {tokens[i]} at {line}."
            )
    else:
        raise ValueError(
            f"Expected floating-point value but found EOL at {line}."
        )

    i += 1
    return i == len(tokens)


def is_group(contents, i):
    """
    Handle:

    group = *(startgroupline / emptyline)   ; ... and possibly more
                                            ; user-agent lines
        *(rule / emptyline)                 ; followed by rules relevant
                                            ; for the preceding
                                            ; user-agent lines
    """
    if not len(contents):
        return False, i
    # i += 1

    # *(startgroupline / emptyline)
    group_found = False
    while i < len(contents):
        if is_startgroupline(contents[i]):
            i += 1
            group_found = True
        elif is_emptyline(contents[i]):
            i += 1
            group_found = True
        else:
            break
    if group_found:
        return True, i

    # *(rule / emptyline)
    while i < len(contents):
        if is_rule(contents[i]):
            i += 1
            group_found = True
        elif is_emptyline(contents[i]):
            i += 1
            group_found = True
        else:
            break
    if group_found:
        return True, i

    while i < len(contents):
        if is_nonstandard_rule(contents[i]):
            i += 1
            group_found = True
        elif is_emptyline(contents[i]):
            i += 1
            group_found = True
        else:
            break
    if group_found:
        return True, i

    while i < len(contents):
        if contents[i].lower().startswith('sitemap'):
            i += 1
            
            group_found = True
        elif is_emptyline(contents[i]):
            i += 1
            group_found = True
        else:
            break
    if group_found:
        return True, i

    raise RuntimeError(
        f"Expected to find a startgroupline, a rule, a crawl-delay, or a sitemap, but found {contents[i]}."
    )


def is_robotstxt(contents):
    """
    Handle:

    robotstxt = *(group / emptyline)

    """
    i = 0
    while i < len(contents):
        ret, i = is_group(contents, i)
        if not ret:
            return False
        if i == len(contents):
            return True


def is_valid(path):
    if not os.path.isfile(path):
        raise FileNotFoundError(f"File not found: {path}")
    with open(path, 'r', encoding='utf-8') as file:
        contents = [line.strip() for line in file.read().split('\n') if line.strip()]
    return is_robotstxt(contents)


def main():
    parser = argparse.ArgumentParser(description="Validate a robots.txt file.")
    parser.add_argument(
        "path",
        nargs="?",
        default="./robots.txt",
        help="Path to robots.txt file (default: ./robots.txt)"
    )
    args = parser.parse_args()
    is_valid(args.path)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Error: {e}")
        exit(1)
