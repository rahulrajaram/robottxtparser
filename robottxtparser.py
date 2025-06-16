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

Restrictions:
1. There is basic support for Crawl-delay, but it must appear within a user-agent rules group
2. All Sitemaps must appear towards the end
"""
import os
import re

import json

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
    if not token.startswith('/') and not token.startswith('*'):
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

    allow_disallow_label = None
    # ("allow" / "disallow") *WS ":"
    if i < len(tokens) and tokens[i].lower() in ['allow', 'disallow']:
        allow_disallow_label = tokens[i].lower()
        i += 1
        while i < len(tokens):
            if not is_WS(tokens[i]):
                break
            i += 1
        if i == len(tokens) or not tokens[i] != ":":
            return False, {}
        i += 1
    elif i < len(tokens) and tokens[i].lower() in ['allow:', 'disallow:']:
        allow_disallow_label = tokens[i].split(':')[0].lower()
        i += 1
    else:
        return False, {}
    
    # *WS
    while i < len(tokens):
        if not is_WS(tokens[i]):
            break
        i += 1

    # (path-pattern / empty-pattern) EOL
    path_pattern = None
    if i < len(tokens) and is_path_pattern(tokens[i]):
        path_pattern = tokens[i]
        i += 1
    else:       
        while i < len(tokens):
            if not is_WS(tokens[i]):
                break
            i += 1
    return (
        i == len(tokens),
        {
            allow_disallow_label: path_pattern
        }
    )


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
            return False, {}
    elif i < len(tokens) and tokens[i].lower() == 'user-agent:':
        i += 1
    else:
        return False, {}

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

    user_agent = []
    while i < len(tokens):
        if not is_product_token(tokens[i]):
            raise ValueError(
                f"Expected identifier but found {tokens[i]}. "
                "Identifiers follow the regex r'^[-a-zA-Z0-9_]+[\\*]{1}$'"
            )
        user_agent.append(tokens[i])
        i += 1
    user_agent = " ".join(user_agent)

    return (
        i == len(tokens),
        user_agent
    )


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
            return False, None
    elif i < len(tokens) and tokens[i].lower() in [
        "crawl-delay:"
    ]:
        i += 1
    else:
        return False, None

    # *WS
    while i < len(tokens):
        if not is_WS(tokens[i]):
            break
        i += 1

    # product-token EOL
    if i < len(tokens):
        try:
            crawl_delay = float(tokens[i])
            i += 1
            return i == len(tokens), crawl_delay
        except ValueError:
            raise ValueError(
                f"Expected floating-point value but found {tokens[i]} at {line}."
            )
    else:
        raise ValueError(
            f"Expected floating-point value but found EOL at {line}."
        )


def is_group(contents, i, current_group, ignore_unsupported=False):
    """
    Handle:

    group = *(startgroupline / emptyline)   ; ... and possibly more
                                            ; user-agent lines
        *(rule / emptyline)                 ; followed by rules relevant
                                            ; for the preceding
                                            ; user-agent lines
    """
    if not len(contents):
        return False, i, {}
    # i += 1

    current_user_agent = None
    if current_group:
        current_user_agent = list(current_group.keys())[0]
    # *(startgroupline / emptyline)
    group_found = False
    while i < len(contents):
        ret, user_agent = is_startgroupline(contents[i])
        if ret:
            current_group = {
                user_agent: {
                    "allow": set(),
                    "disallow": set(),
                }
            }
            i += 1
            group_found = True
        elif is_emptyline(contents[i]):
            i += 1
            group_found = True
        else:
            break
    if group_found:
        return True, i, current_group

    # *(rule / emptyline)
    while i < len(contents):
        ret, allow_disallow = is_rule(contents[i])
        if ret:
            i += 1
            if allow_disallow.get('allow'):
                current_group[current_user_agent]['allow'].add(allow_disallow['allow'])
            if allow_disallow.get('disallow'):
                current_group[current_user_agent]['disallow'].add(allow_disallow['disallow'])
            group_found = True
        elif is_emptyline(contents[i]):
            i += 1
            group_found = True
        else:
            break
    if group_found:
        return True, i, current_group

    while i < len(contents):
        ret, crawl_delay = is_nonstandard_rule(contents[i])
        if ret:
            if not current_user_agent or current_user_agent == 'sitemaps':
                if not ignore_unsupported:
                    raise RuntimeError(
                        "Found crawl-delay definition after sitemap definition.\n"
                        f"\n\t{contents[i]}\n"
                        "All crawl-delay definitions must appear within a user-agent group definition. "
                        "All sitemap definitions must appear at the end."
                    )
                else:
                    return True, i + 1, current_group
            i += 1
            current_group[current_user_agent]['crawl-delay'] = crawl_delay
            group_found = True
        elif is_emptyline(contents[i]):
            i += 1
            group_found = True
        else:
            break
    if group_found:
        return True, i, current_group

    current_group = {
        'sitemaps': set()
    }
    while i < len(contents):
        if contents[i].lower().startswith('sitemap:'):       
            current_group['sitemaps'].add(contents[i][8:].strip().split('sitemap:')[0])
            i += 1

            group_found = True
        elif is_emptyline(contents[i]):
            i += 1
            group_found = True
        else:
            break
    if group_found:
        return True, i, current_group

    if not ignore_unsupported:
        raise RuntimeError(
            f"Expected to find a startgroupline, a rule, a crawl-delay, or a sitemap, but found {contents[i]}."
        )
    return True, i + 1, current_group


def is_robotstxt(contents, ignore_unsupported=False):
    """
    Handle:

    robotstxt = *(group / emptyline)

    """
    i = 0
    global_map = {
        'user-agent-groups': dict(),
        'sitemaps': set(),
    }

    current_group = {}
    while i < len(contents):
        ret, i, current_group = is_group(contents, i, current_group, ignore_unsupported)
        if not ret:
            return False
        if not current_group:
            continue
        if current_group:
            user_agent_key = list(current_group.keys())[0]
            global_map['user-agent-groups'][user_agent_key] = current_group[user_agent_key]
        if current_group.get('sitemaps'):
            global_map['sitemaps'] = current_group['sitemaps']
        if i == len(contents):
            return True, global_map


def is_valid(path, ignore_unsupported):
    if not os.path.isfile(path):
        raise FileNotFoundError(f"File not found: {path}")
    with open(path, 'r', encoding='utf-8') as file:
        contents = [line.strip() for line in file.read().split('\n') if line.strip()]
    ret, global_map = is_robotstxt(contents, ignore_unsupported)
    return ret, global_map


def validate_url(robot_file, url):
    ret, global_map = is_valid(robot_file)
    

def main(): 
    parser = argparse.ArgumentParser(description="Validate a robots.txt file.")
    parser.add_argument(
        "path",
        nargs="?",
        default="./robots.txt",
        help="Path to robots.txt file (default: ./robots.txt)"
    )
    parser.add_argument(
        "-u", "--url",
        help="Path to robots.txt file (default: ./robots.txt)"
    )
    parser.add_argument(
        "-s", "--skip-validation",
        help="Skip validation of the robots.txt file during URL matching"
    )
    parser.add_argument(
        "-i", "--ignore-unsupported",
        action='store_true',
        help="Ignore rules like Noindex rather than erroring on encountering them"
    )
    parser.add_argument(
        "-d", "--debug",
        action='store_true',
        help="Emit debug logs"
    )
    args = parser.parse_args()

    try:
        if args.skip_validation and args.url:
            validate_url(args.path, args.url)
        elif args.path:
            is_valid(args.path, args.ignore_unsupported)
    except Exception as e:
        if args.debug:
            import traceback
            print(traceback.print_exc())
        raise e


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Error: {e}")
        exit(1)
