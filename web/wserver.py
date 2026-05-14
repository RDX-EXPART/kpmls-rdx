from logging import getLogger, FileHandler, StreamHandler, INFO, basicConfig
from time import sleep
from qbittorrentapi import NotFound404Error, Client as qbClient
from aria2p import API as ariaAPI, Client as ariaClient
from flask import Flask, request

from web.nodes import make_tree

app = Flask(__name__)

aria2 = ariaAPI(ariaClient(host="http://localhost", port=6800, secret=""))

basicConfig(format="[%(asctime)s] [%(levelname)s] - %(message)s",
            datefmt="%d-%b-%y %I:%M:%S %p",
            handlers=[FileHandler('log.txt'), StreamHandler()],
            level=INFO)

LOGGER = getLogger(__name__)

page = """
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta http-equiv="X-UA-Compatible" content="IE=edge" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Torrent File Selector</title>
    <link rel="icon" href="https://graph.org/file/1a6ad157f55bc42b548df.png" type="image/jpg">
    <script
      src="https://code.jquery.com/jquery-3.5.1.slim.min.js"
      integrity="sha256-4+XzXVhsDmqanXGHaHvgh1gMQKX40OUvDEBTu8JcmNs="
      crossorigin="anonymous"
    ></script>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link
      href="https://fonts.googleapis.com/css2?family=Ubuntu:ital,wght@0,300;0,400;0,500;0,700;1,300;1,400;1,500;1,700&display=swap"
      rel="stylesheet"
    />
    <link
      rel="stylesheet"
      href="https://pro.fontawesome.com/releases/v5.10.0/css/all.css"
      integrity="sha384-AYmEC3Yw5cVb3ZcuHtOA93w35dYTsvhLPVnYs9eStHfGJvOvKxVfELGroGkvsg+p"
      crossorigin="anonymous"
    />
<style>

*{
    margin: 0;
    padding: 0;
    box-sizing: border-box;
    font-family: "Ubuntu", sans-serif;
    list-style: none;
    text-decoration: none;
    outline: none !important;
    color: white;
}

body{
    background-color: #0D1117;
}

header{
    margin: 3vh 1vw;
    padding: 0.5rem 1rem 0.5rem 1rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-bottom: #161B22;
    border-radius: 30px;
    background-color: #161B22;
    border: 2px solid rgba(255, 255, 255, 0.11);
}

header:hover, section:hover{
    box-shadow: 0px 0px 15px black;
}

.brand{
    display: flex;
    align-items: center;
}

img{
    width: 2.5rem;
    height: 2.5rem;
    border: 2px solid black;
    border-radius: 50%;
}

.name{
    margin-left: 1vw;
    font-size: 1.5rem;
}

.intro{
    text-align: center;
    margin-bottom: 2vh;
    margin-top: 1vh;
}

.social a{
    font-size: 1.5rem;
    padding-left: 1vw;
}

.social a:hover, .brand:hover{
    filter: invert(0.3);
}

section{
    margin: 0vh 1vw;
    margin-bottom: 10vh;
    padding: 1vh 3vw;
    display: flex;
    flex-direction: column;
    border: 2px solid rgba(255, 255, 255, 0.11);
    border-radius: 20px;
    background-color: #161B22 ;
}

li:nth-child(1){
    padding: 1rem 1rem 0.5rem 1rem;
}

li:nth-child(n+1){
    padding-left: 1rem;
}

li label{
    padding-left: 0.5rem;
}

li{
    padding-bottom: 0.5rem;
}

span{
    margin-right: 0.5rem;
    cursor: pointer;
    user-select: none;
    transition: transform 200ms ease-out;
}

span.active{
    transform: rotate(90deg);
    -ms-transform: rotate(90deg); /* for IE  */
    -webkit-transform: rotate(90deg);/* for browsers supporting webkit (such as chrome, firefox, safari etc.). */
    display: inline-block;
}

ul{
    margin: 1vh 1vw 1vh 1vw;
    padding: 0 0 0.5rem 0;
    border: 2px solid black;
    border-radius: 20px;
    background-color: #1c2129;
    overflow: hidden;
}

input[type="checkbox"]{
    cursor: pointer;
    user-select: none;
}

input[type="submit"] {
    border-radius: 20px;
    margin: 2vh auto 1vh auto;
    width: 50%;
    display: block;
    height: 5.5vh;
    border: 2px solid rgba(255, 255, 255, 0.11);
    background-color: #0D1117;
    font-size: 16px;
    font-weight: 500;
}

input[type="submit"]:hover, input[type="submit"]:focus{
    background-color: rgba(255, 255, 255, 0.068);
    cursor: pointer;
}

@media (max-width: 768px){
    input[type="submit"]{
        width: 100%;
    }
}

#treeview .parent {
    position: relative;
}

#treeview .parent > ul {
    display: none;
}

#sticks {
  margin: 0vh 1vw;
  margin-bottom: 1vh;
  padding: 1vh 3vw;
  display: flex;
  flex-direction: column;
  border: 2px solid rgba(255, 255, 255, 0.11);
  border-radius: 20px;
  background-color: #161b22;
  align-items: center;
}

#sticks.stick {
  position: sticky;
  top: 0;
  z-index: 10000;
}
</style>
<script>
function s_validate() {
    if ($("input[name^='filenode_']:checked").length == 0) {
        alert("Select one file at least!");
        return false;
        }
    }
</script>
</head>
<body>
  <!--© Designed and coded by @KPSBots-Telegram-->
    <header>
      <div class="brand">
        <img
          src="https://graph.org/file/1a6ad157f55bc42b548df.png"
          alt="logo"
        />
        <a href="https://telegram.me/KPSBots">
          <h2 class="name">Bittorrent Selection</h2>
        </a>
      </div>
      <div class="social">
        <a href="https://github.com/Tamilupdates/KPSML-X"><i class="fab fa-github"></i></a>
        <a href="https://telegram.me/KPSBots"><i class="fab fa-telegram"></i></a>
      </div>
    </header>
    <div id="sticks">
        <h4>Selected files: <b id="checked_files">0</b> of <b id="total_files">0</b></h4>
        <h4>Selected files size: <b id="checked_size">0</b> of <b id="total_size">0</b></h4>
    </div>
      <section>
      <form action="{form_url}" onsubmit="return s_validate()" method="POST">
       {My_content}
       <input type="submit" name="Select these files ;)">
      </form>
    </section>

    <script>
      $(document).ready(function () {
        docready();
        var tags = $("li").filter(function () {
          return $(this).find("ul").length !== 0;
        });

        tags.each(function () {
          $(this).addClass("parent");
        });

        $("body").find("ul:first-child").attr("id", "treeview");
        $(".parent").prepend("<span>▶</span>");

        $("span").click(function (e) {
          e.stopPropagation();
          e.stopImmediatePropagation();
          $(this).parent( ".parent" ).find(">ul").toggle("slow");
          if ($(this).hasClass("active")) $(this).removeClass("active");
          else $(this).addClass("active");
        });
      });

      if(document.getElementsByTagName("ul").length >= 10){
        var labels = document.querySelectorAll("label");
        //Shorting the file/folder names
        labels.forEach(function (label) {
            if (label.innerText.toString().split(" ").length >= 9) {
                let FirstPart = label.innerText
                    .toString()
                    .split(" ")
                    .slice(0, 5)
                    .join(" ");
                let SecondPart = label.innerText
                    .toString()
                    .split(" ")
                    .splice(-5)
                    .join(" ");
                label.innerText = `${FirstPart}... ${SecondPart}`;
            }
            if (label.innerText.toString().split(".").length >= 9) {
                let first = label.innerText
                    .toString()
                    .split(".")
                    .slice(0, 5)
                    .join(" ");
                let second = label.innerText
                    .toString()
                    .split(".")
                    .splice(-5)
                    .join(".");
                label.innerText = `${first}... ${second}`;
            }
        });
    }
    </script>

<script>
$('input[type="checkbox"]').change(function(e) {
  var checked = $(this).prop("checked"),
      container = $(this).parent(),
      siblings = container.siblings();
/*
  $(this).attr('value', function(index, attr){
     return attr == 'yes' ? 'noo' : 'yes';
  });
*/
  container.find('input[type="checkbox"]').prop({
    indeterminate: false,
    checked: checked
  });
  function checkSiblings(el) {
    var parent = el.parent().parent(),
        all = true;
    el.siblings().each(function() {
      let returnValue = all = ($(this).children('input[type="checkbox"]').prop("checked") === checked);
      return returnValue;
    });

    if (all && checked) {
      parent.children('input[type="checkbox"]').prop({
        indeterminate: false,
        checked: checked
      });
      checkSiblings(parent);
    } else if (all && !checked) {
      parent.children('input[type="checkbox"]').prop("checked", checked);
      parent.children('input[type="checkbox"]').prop("indeterminate", (parent.find('input[type="checkbox"]:checked').length > 0));
      checkSiblings(parent);
    } else {
      el.parents("li").children('input[type="checkbox"]').prop({
        indeterminate: true,
        checked: false
      });
    }
  }
  checkSiblings(container);
});
</script>
<script>
    function docready () {
        $("label[for^='filenode_']").css("cursor", "pointer");
        $("label[for^='filenode_']").click(function () {
            $(this).prev().click();
        });
        checked_size();
        checkingfiles();
        var total_files = $("label[for^='filenode_']").length;
        $("#total_files").text(total_files);
        var total_size = 0;
        var ffilenode = $("label[for^='filenode_']");
        ffilenode.each(function () {
            var size = parseFloat($(this).data("size"));
            total_size += size;
            $(this).append(" - " + humanFileSize(size));
        });
        $("#total_size").text(humanFileSize(total_size));
    };
    function checked_size() {
        var checked_size = 0;
        var checkedboxes = $("input[name^='filenode_']:checked");
        checkedboxes.each(function () {
            var size = parseFloat($(this).data("size"));
            checked_size += size;
        });
        $("#checked_size").text(humanFileSize(checked_size));
    }
    function checkingfiles() {
        var checked_files = $("input[name^='filenode_']:checked").length;
        $("#checked_files").text(checked_files);
    }
    $("input[name^='foldernode_']").change(function () {
        checkingfiles();
        checked_size();
    });
    $("input[name^='filenode_']").change(function () {
        checkingfiles();
        checked_size();
    });
    function humanFileSize(size) {
        var i = -1;
        var byteUnits = [' kB', ' MB', ' GB', ' TB', 'PB', 'EB', 'ZB', 'YB'];
        do {
            size = size / 1024;
            i++;
        } while (size > 1024);
        return Math.max(size, 0).toFixed(1) + byteUnits[i];
    }
    function sticking() {
        var window_top = $(window).scrollTop();
        var div_top = $('.brand').offset().top;
        if (window_top > div_top) {
            $('#sticks').addClass('stick');
        } else {
            $('#sticks').removeClass('stick');
        }
    }
    $(function () {
        $(window).scroll(sticking);
        sticking();
    });
</script>
</body>
</html>
"""

code_page = """
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta http-equiv="X-UA-Compatible" content="IE=edge" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Torrent Code Checker</title>
    <link rel="icon" href="https://graph.org/file/1a6ad157f55bc42b548df.png" type="image/jpg">
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link
      href="https://fonts.googleapis.com/css2?family=Ubuntu:ital,wght@0,300;0,400;0,500;0,700;1,300;1,400;1,500;1,700&display=swap"
      rel="stylesheet"
    />
    <link
      rel="stylesheet"
      href="https://pro.fontawesome.com/releases/v5.10.0/css/all.css"
      integrity="sha384-AYmEC3Yw5cVb3ZcuHtOA93w35dYTsvhLPVnYs9eStHfGJvOvKxVfELGroGkvsg+p"
      crossorigin="anonymous"
    />
    <style>
     *{
    margin: 0;
    padding: 0;
    box-sizing: border-box;
    font-family: "Ubuntu", sans-serif;
    list-style: none;
    text-decoration: none;
    color: white;
}

body{
    background-color: #0D1117;
}

header{
    margin: 3vh 1vw;
    padding: 0.5rem 1rem 0.5rem 1rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-bottom: #161B22;
    border-radius: 30px;
    background-color: #161B22;
    border: 2px solid rgba(255, 255, 255, 0.11);
}

header:hover, section:hover{
    box-shadow: 0px 0px 15px black;
}

.brand{
    display: flex;
    align-items: center;
}

img{
    width: 2.5rem;
    height: 2.5rem;
    border: 2px solid black;
    border-radius: 50%;
}

.name{
    color: white;
    margin-left: 1vw;
    font-size: 1.5rem;
}

.intro{
    text-align: center;
    margin-bottom: 2vh;
    margin-top: 1vh;
}

.social a{
    font-size: 1.5rem;
    color: white;
    padding-left: 1vw;
}

.social a:hover, .brand:hover{
    filter: invert(0.3);
}

section{
    margin: 0vh 1vw;
    margin-bottom: 10vh;
    padding: 1vh 3vw;
    display: flex;
    flex-direction: column;
    border: 2px solid rgba(255, 255, 255, 0.11);
    border-radius: 20px;
    background-color: #161B22 ;
    color: white;
}

section form{
    display: flex;
    margin-left: auto;
    margin-right: auto;
    flex-direction: column;
}

section div{
    background-color: #0D1117;
    border-radius: 20px;
    max-width: fit-content;
    padding: 0.7rem;
    margin-top: 2vh;
}

section label{
    font-size: larger;
    font-weight: 500;
    margin: 0 0 0.5vh 1.5vw;
    display: block;
}

section input[type="text"]{
    border-radius: 20px;
    outline: none;
    width: 50vw;
    height: 4vh;
    padding: 1rem;
    margin: 0.5vh;
    border: 2px solid rgba(255, 255, 255, 0.11);
    background-color: #3e475531;
    box-shadow: inset 0px 0px 10px black;
}

section input[type="text"]:focus{
    border-color: rgba(255, 255, 255, 0.404);
}

section button{
    border-radius: 20px;
    margin-top: 1vh;
    width: 100%;
    height: 5.5vh;
    border: 2px solid rgba(255, 255, 255, 0.11);
    background-color: #0D1117;
    color: white;
    font-size: 16px;
    font-weight: 500;
    cursor: pointer;
    transition: background-color 200ms ease;
}

section button:hover, section button:focus{
    background-color: rgba(255, 255, 255, 0.068);
}

section span{
    display: block;
    font-size: x-small;
    margin: 1vh;
    font-weight: 100;
    font-style: italic;
    margin-left: 23%;
    margin-right: auto;
    margin-bottom: 2vh;
}

@media (max-width: 768px) {
    section form{
        flex-direction: column;
        width: 90vw;
    }

    section div{
        max-width: 100%;
        margin-bottom: 1vh;
    }

    section label{
        margin-left: 3vw;
        margin-top: 1vh;
    }

    section input[type="text"]{
        width: calc(100% - 0.3rem);
    }

    section button{
        width: 100%;
        height: 5vh;
        display: block;
        margin-left: auto;
        margin-right: auto;
    }

    section span{
        margin-left: 5%;
    }
}
    </style>
  </head>
<body>
   <!--© Designed and coded by @KPSBots-Telegram-->
    <header>
      <div class="brand">
        <img
          src="https://graph.org/file/1a6ad157f55bc42b548df.png"
          alt="logo"
        />
        <a href="https://telegram.me/KPSBots">
          <h2 class="name">Bittorrent Selection</h2>
        </a>
      </div>
      <div class="social">
        <a href="https://github.com/Tamilupdates/KPSML-X"><i class="fab fa-github"></i></a>
        <a href="https://telegram.me/KPSBots"><i class="fab fa-telegram"></i></a>
      </div>
    </header>
    <section>
      <form action="{form_url}">
        <div>
          <label for="pin_code">Pin Code :</label>
          <input
            type="text"
            name="pin_code"
            placeholder="Enter the code that you have got from Telegram to access the Torrent"
          />
        </div>
        <button type="submit" class="btn btn-primary">Submit</button>
      </form>
          <span
            >* Dont mess around. Your download will get messed up.</
          >
    </section>
</body>
</html>
"""


def re_verfiy(paused, resumed, client, hash_id):

    paused = paused.strip()
    resumed = resumed.strip()
    if paused:
        paused = paused.split("|")
    if resumed:
        resumed = resumed.split("|")

    k = 0
    while True:
        res = client.torrents_files(torrent_hash=hash_id)
        verify = True
        for i in res:
            if str(i.id) in paused and i.priority != 0:
                verify = False
                break
            if str(i.id) in resumed and i.priority == 0:
                verify = False
                break
        if verify:
            break
        LOGGER.info("Reverification Failed! Correcting stuff...")
        client.auth_log_out()
        sleep(1)
        client = qbClient(host="localhost", port="8090")
        try:
            client.torrents_file_priority(
                torrent_hash=hash_id, file_ids=paused, priority=0)
        except NotFound404Error as e:
            raise NotFound404Error from e
        except Exception as e:
            LOGGER.error(f"{e} Errored in reverification paused!")
        try:
            client.torrents_file_priority(
                torrent_hash=hash_id, file_ids=resumed, priority=1)
        except NotFound404Error as e:
            raise NotFound404Error from e
        except Exception as e:
            LOGGER.error(f"{e} Errored in reverification resumed!")
        k += 1
        if k > 5:
            return False
    LOGGER.info(f"Verified! Hash: {hash_id}")
    return True


@app.route('/app/files/<string:id_>', methods=['GET'])
def list_torrent_contents(id_):

    if "pin_code" not in request.args.keys():
        return code_page.replace("{form_url}", f"/app/files/{id_}")

    pincode = ""
    for nbr in id_:
        if nbr.isdigit():
            pincode += str(nbr)
        if len(pincode) == 4:
            break
    if request.args["pin_code"] != pincode:
        return "<h1>Incorrect pin code</h1>"

    if len(id_) > 20:
        client = qbClient(host="localhost", port="8090")
        res = client.torrents_files(torrent_hash=id_)
        cont = make_tree(res)
        client.auth_log_out()
    else:
        res = aria2.client.get_files(id_)
        cont = make_tree(res, True)
    return page.replace("{My_content}", cont[0]).replace("{form_url}", f"/app/files/{id_}?pin_code={pincode}")


@app.route('/app/files/<string:id_>', methods=['POST'])
def set_priority(id_):

    data = dict(request.form)
    resume = ""
    if len(id_) > 20:
        pause = ""

        for i, value in data.items():
            if "filenode" in i:
                node_no = i.split("_")[-1]

                if value == "on":
                    resume += f"{node_no}|"
                else:
                    pause += f"{node_no}|"

        pause = pause.strip("|")
        resume = resume.strip("|")

        client = qbClient(host="localhost", port="8090")

        try:
            client.torrents_file_priority(
                torrent_hash=id_, file_ids=pause, priority=0)
        except NotFound404Error as e:
            raise NotFound404Error from e
        except Exception as e:
            LOGGER.error(f"{e} Errored in paused")
        try:
            client.torrents_file_priority(
                torrent_hash=id_, file_ids=resume, priority=1)
        except NotFound404Error as e:
            raise NotFound404Error from e
        except Exception as e:
            LOGGER.error(f"{e} Errored in resumed")
        sleep(1)
        if not re_verfiy(pause, resume, client, id_):
            LOGGER.error(f"Verification Failed! Hash: {id_}")
        client.auth_log_out()
    else:
        for i, value in data.items():
            if "filenode" in i and value == "on":
                node_no = i.split("_")[-1]
                resume += f'{node_no},'

        resume = resume.strip(",")

        res = aria2.client.change_option(id_, {'select-file': resume})
        if res == "OK":
            LOGGER.info(f"Verified! GID: {id_}")
        else:
            LOGGER.info(f"Verification Failed! Report! GID: {id_}")
    return list_torrent_contents(id_)


_STREAM_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>{title} — KPSML-X Stream</title>
<link rel="icon" href="https://graph.org/file/1a6ad157f55bc42b548df.png" type="image/jpg"/>
<link href="https://fonts.googleapis.com/css2?family=Ubuntu:wght@300;400;500;700&display=swap" rel="stylesheet"/>
<style>
*{{margin:0;padding:0;box-sizing:border-box;font-family:"Ubuntu",sans-serif;color:#fff}}
body{{background:#0D1117;min-height:100vh;display:flex;flex-direction:column;align-items:center;padding:2rem 1rem}}
header{{width:100%;max-width:860px;display:flex;align-items:center;gap:1rem;background:#161B22;border:2px solid rgba(255,255,255,.11);border-radius:20px;padding:.7rem 1.2rem;margin-bottom:2rem}}
header img{{width:2.2rem;height:2.2rem;border-radius:50%}}
header h2{{font-size:1.1rem;font-weight:500}}
.card{{width:100%;max-width:860px;background:#161B22;border:2px solid rgba(255,255,255,.11);border-radius:20px;overflow:hidden}}
.player-wrap{{width:100%;background:#000;display:flex;justify-content:center;align-items:center;min-height:200px}}
video,audio{{width:100%;max-height:480px;outline:none}}
.info{{padding:1.5rem}}
.filename{{font-size:1rem;font-weight:500;word-break:break-all;color:#e6edf3;margin-bottom:.4rem}}
.meta{{font-size:.8rem;color:#8b949e;margin-bottom:1.4rem}}
.btns{{display:flex;flex-wrap:wrap;gap:.7rem}}
.btn{{display:inline-flex;align-items:center;gap:.5rem;padding:.65rem 1.3rem;border-radius:12px;border:2px solid rgba(255,255,255,.15);background:#0D1117;color:#fff;text-decoration:none;font-size:.9rem;font-weight:500;cursor:pointer;transition:background 200ms,border-color 200ms}}
.btn:hover{{background:rgba(255,255,255,.08);border-color:rgba(255,255,255,.3)}}
.btn.primary{{border-color:#2d68ff;background:rgba(45,104,255,.15)}}
.btn.primary:hover{{background:rgba(45,104,255,.3)}}
.vlc-note{{margin-top:1.2rem;font-size:.75rem;color:#8b949e;border-top:1px solid rgba(255,255,255,.07);padding-top:1rem}}
.vlc-note code{{background:#0D1117;padding:.15rem .4rem;border-radius:6px;font-size:.73rem;word-break:break-all}}
footer{{margin-top:2rem;font-size:.75rem;color:#8b949e;text-align:center}}
</style>
</head>
<body>
<header>
  <img src="https://graph.org/file/1a6ad157f55bc42b548df.png" alt="logo"/>
  <h2>KPSML-X &mdash; Stream / Download</h2>
</header>
<div class="card">
  <div class="player-wrap">
    {player}
  </div>
  <div class="info">
    <div class="filename">{filename}</div>
    <div class="meta">{meta}</div>
    <div class="btns">
      <a class="btn primary" href="{dl_url}" download="{filename}">📥 Download</a>
      <a class="btn" href="{stream_url}" target="_blank">🌐 Open Stream</a>
      <a class="btn" href="vlc://{raw_stream_url}">🎬 Open in VLC</a>
    </div>
    <div class="vlc-note">
      <b>VLC / Media Player URL:</b><br/>
      <code>{raw_stream_url}</code>
    </div>
  </div>
</div>
<footer>&copy; KPSML-X &mdash; Temporary link, valid 24 hours</footer>
</body>
</html>"""


_STREAM_EXPIRED_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Link Expired — KPSML-X</title>
<link href="https://fonts.googleapis.com/css2?family=Ubuntu:wght@400;500&display=swap" rel="stylesheet"/>
<style>
*{{margin:0;padding:0;box-sizing:border-box;font-family:"Ubuntu",sans-serif;color:#fff}}
body{{background:#0D1117;min-height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:2rem}}
.icon{{font-size:4rem;margin-bottom:1rem}}
h1{{font-size:1.5rem;margin-bottom:.6rem}}
p{{color:#8b949e;font-size:.9rem}}
</style>
</head>
<body>
<div class="icon">⏳</div>
<h1>Link Expired or Invalid</h1>
<p>This temporary streaming link has expired (24 h) or is invalid.<br/>
Re-download / re-leech the file to get a fresh link.</p>
</body>
</html>"""


@app.route('/stream/<string:token>')
def stream_tg_file(token):
    """
    Streaming / download proxy for leeched Telegram files.
    - No ?dl=1   → show HTML player page
    - ?dl=1      → direct stream (for download / VLC)
    """
    import asyncio
    import queue as _q
    from os import environ as _env
    from flask import request as _req, redirect, Response, stream_with_context

    try:
        from bot.helper.ext_utils.stream_link import get_stream_data
        data = get_stream_data(token)
    except Exception as e:
        LOGGER.error(f"stream_link import error: {e}")
        data = None

    if not data:
        return _STREAM_EXPIRED_PAGE, 404

    file_id, filename, mime_type = data
    BOT_TOKEN = _env.get('BOT_TOKEN', '')

    # ── Build URLs for the HTML page ──────────────────────────────────────────
    raw_stream_url = _req.url.split('?')[0] + '?dl=1'
    dl_url = raw_stream_url

    # ── Direct stream / download path (?dl=1 or VLC) ──────────────────────────
    want_direct = bool(_req.args.get('dl'))
    user_agent = _req.headers.get('User-Agent', '').lower()
    # VLC, mpv, wget, curl → stream directly
    is_player_ua = any(p in user_agent for p in ('vlc', 'mpv', 'wget', 'curl', 'python-requests'))

    if want_direct or is_player_ua:
        # 1️⃣ Try Bot API redirect (instant, works for files ≤ 20 MB)
        if BOT_TOKEN:
            try:
                import requests as _requests
                r = _requests.get(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/getFile",
                    params={"file_id": file_id},
                    timeout=10
                )
                j = r.json()
                if j.get('ok') and j['result'].get('file_path'):
                    cdn = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{j['result']['file_path']}"
                    disposition = 'attachment' if want_direct else 'inline'
                    resp = redirect(cdn)
                    resp.headers['Content-Disposition'] = f'{disposition}; filename="{filename}"'
                    return resp
            except Exception as e:
                LOGGER.warning(f"Bot API getFile fallback to Pyrogram stream: {e}")

        # 2️⃣ Pyrogram stream_media fallback (works for ANY size)
        try:
            from bot import bot, bot_loop

            # asyncio.Queue lives in bot_loop; consumer fetches via run_coroutine_threadsafe
            async def _make_queue():
                return asyncio.Queue(maxsize=20)

            stream_q = asyncio.run_coroutine_threadsafe(_make_queue(), bot_loop).result(timeout=10)

            async def _producer():
                try:
                    async for chunk in bot.stream_media(file_id, limit=256):
                        await stream_q.put(chunk)
                except Exception as pe:
                    LOGGER.error(f"Pyrogram stream_media error: {pe}")
                finally:
                    await stream_q.put(None)   # sentinel

            asyncio.run_coroutine_threadsafe(_producer(), bot_loop)

            def _generate():
                while True:
                    chunk = asyncio.run_coroutine_threadsafe(
                        stream_q.get(), bot_loop
                    ).result(timeout=120)
                    if chunk is None:
                        break
                    yield chunk

            disposition = 'attachment' if want_direct else 'inline'
            headers = {
                'Content-Type': mime_type or 'application/octet-stream',
                'Content-Disposition': f'{disposition}; filename="{filename}"',
                'Accept-Ranges': 'none',
                'Cache-Control': 'no-cache',
            }
            return Response(stream_with_context(_generate()), headers=headers)

        except Exception as e:
            LOGGER.error(f"Pyrogram stream error: {e}")
            return f"<h1>❌ Streaming error: {e}</h1>", 500

    # ── HTML player page ───────────────────────────────────────────────────────
    if mime_type.startswith('video'):
        player = f'<video controls autoplay preload="metadata" src="{dl_url}"></video>'
        meta = f'Video &bull; {mime_type}'
    elif mime_type.startswith('audio'):
        player = f'<audio controls autoplay preload="metadata" src="{dl_url}"></audio>'
        meta = f'Audio &bull; {mime_type}'
    else:
        player = '<div style="padding:3rem;font-size:3rem;text-align:center">📄</div>'
        meta = mime_type or 'File'

    page = _STREAM_PAGE.format(
        title=filename,
        filename=filename,
        meta=meta,
        dl_url=dl_url,
        stream_url=_req.url,
        raw_stream_url=raw_stream_url,
        player=player,
    )
    return page, 200


@app.route('/')
def homepage():
    return """
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta http-equiv="X-UA-Compatible" content="IE=edge" />
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link
      href="https://fonts.googleapis.com/css2?family=Ubuntu:ital,wght@0,300;0,400;0,500;0,700;1,300;1,400;1,500;1,700&display=swap"
      rel="stylesheet"
    />
    <style>
        body {
            background-color: #0D1117;
            color: white;
            font-family: "Ubuntu", sans-serif;
        }
        .header {
            background-color: black;
            text-align: center;
            width: 100%;
            padding: 1px;
        }
        .footer {
            background-color: black;
            padding: 10px;
            text-align: center;
            position: absolute;
            bottom: 0;
            width: 100%;
        }
        .content {
            padding: 20px;
            text-align: center;
        }
        .button {
            background-color: #0001f0;
            color: white;
            padding: 10px 20px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
        }
        .image {
            border-radius: 12px;
            max-width: 100%;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>KPSML-X</h1>
    </div>
    <div class="content">
        <img src="https://graph.org/file/0ff9d5e94a070fe4154c0.jpg" class="image">
        <a href="https://telegram.me/KPSBots" style="text-decoration: none;">
            <button class="button">Join Updates Channel Now</button>
        </a>
    </div>
    <div class="footer">
&copy; <script>document.write(new Date().getFullYear() + '-' + String(new Date().getFullYear() + 1).slice(-2));</script> KPSML-X. All Rights Reserved.
    </div>
</body>
</html>
"""


@app.errorhandler(Exception)
def page_not_found(e):
    return f"<h1>404: Torrent not found! Mostly wrong input. <br><br>Error: {e}</h2>", 404


if __name__ == "__main__":
    app.run()
