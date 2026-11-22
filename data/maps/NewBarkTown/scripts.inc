NewBarkTown_MapScripts::
	.byte 0

@ Project Ditto: proof-of-concept boat link to Kanto. Replace once region travel is designed.
NewBarkTown_EventScript_KantoSailor::
	lock
	faceplayer
	msgbox NewBarkTown_Text_SailToPallet, MSGBOX_YESNO
	goto_if_eq VAR_RESULT, NO, NewBarkTown_EventScript_KantoSailorDecline
	msgbox NewBarkTown_Text_SetSailForPallet, MSGBOX_DEFAULT
	closemessage
	playse SE_SHIP
	warp MAP_PALLET_TOWN, 12, 17
	waitstate
	release
	end

NewBarkTown_EventScript_KantoSailorDecline::
	msgbox NewBarkTown_Text_SailorComeBack, MSGBOX_DEFAULT
	release
	end

NewBarkTown_Text_SailToPallet:
	.string "Ahoy! Would you like to take the boat\n"
	.string "to PALLET TOWN in KANTO?$"

NewBarkTown_Text_SetSailForPallet:
	.string "All aboard! Next stop, PALLET TOWN!$"

NewBarkTown_Text_SailorComeBack:
	.string "No rush. The sea's not going anywhere.$"
