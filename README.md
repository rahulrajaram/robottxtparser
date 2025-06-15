# README

## 1. About `robottxtparser`
Program processes a robot.txt file to verify that it is legal according to the grammar:

```
 robotstxt = *(group / emptyline)
 group = *(startgroupline / emptyline) ; ... and possibly more
                                       ; user-agent lines
        *(rule / emptyline)            ; followed by rules relevant
                                       ; for the preceding
                                       ; user-agent lines

 startgroupline = *WS "user-agent" *WS ":" *WS product-token EOL


 rule = *WS ("allow" / "disallow") *WS ":"
       *WS (path-pattern / empty-pattern) EOL

 ; parser implementors: define additional lines you need (for
 ; example, Sitemaps).

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

## 2. Running
```
python robottxtparser.py [path]
```

Without the `path` argument, the script attempts to find a `./robots.txt` file.
