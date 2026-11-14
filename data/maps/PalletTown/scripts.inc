PalletTown_MapScripts::
	.byte 0

@ Project Ditto: proof-of-concept boat link to Hoenn. Replace once region travel is designed.
PalletTown_EventScript_HoennSailor::
	lock
	faceplayer
	msgbox PalletTown_Text_SailToLittleroot, MSGBOX_YESNO
	goto_if_eq VAR_RESULT, NO, PalletTown_EventScript_HoennSailorDecline
	msgbox PalletTown_Text_SetSailForLittleroot, MSGBOX_DEFAULT
	closemessage
	playse SE_SHIP
	warp MAP_LITTLEROOT_TOWN, 10, 16
	waitstate
	release
	end

PalletTown_EventScript_HoennSailorDecline::
	msgbox PalletTown_Text_SailorComeBack, MSGBOX_DEFAULT
	release
	end

PalletTown_Text_SailToLittleroot:
	.string "Ahoy! Would you like to take the boat\n"
	.string "back to LITTLEROOT TOWN in HOENN?$"

PalletTown_Text_SetSailForLittleroot:
	.string "All aboard! Next stop, LITTLEROOT TOWN!$"

PalletTown_Text_SailorComeBack:
	.string "No rush. The sea's not going anywhere.$"
