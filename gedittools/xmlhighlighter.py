from gettext import gettext as _

import gtk, gtk.glade
from gedittools_configure import GeditToolsConfiguration
import gedit
import re
import os
import glib
import string
from ConfigParser import ConfigParser
from countsearchresults import SearchResultCounter
from meldlauncher import MeldLauncher

class XmlHighlighter():
	def __init__(self, window, opener):
		self._window = window
		self._highlighted_pairs = {} #pairs of highlighted iters
		self._tag_list = {} #all applied tags by document 
		self._tag_lib = {} #all tags to be assigned
		self._opener = opener
				
	def update(self, doc):
		self._current_doc = doc
	
		#initialize tags	
		if self._current_doc and not self._tag_lib.has_key(self._current_doc):
			self._tag_lib[self._current_doc] = []
			self._tag_lib[self._current_doc].append(self._current_doc.create_tag('active_0', foreground="#000000", background="#CCDDFF"))
			self._tag_lib[self._current_doc].append(self._current_doc.create_tag('active_1', foreground="#000000", background="#FFDDCC"))
			self._tag_lib[self._current_doc].append(self._current_doc.create_tag('active_2', foreground="#000000", background="#CCFFDD"))
			self._tag_lib[self._current_doc].append(self._current_doc.create_tag('active_3', foreground="#000000", background="#DDFFCC"))
			self._tag_lib[self._current_doc].append(self._current_doc.create_tag('active_4', foreground="#000000", background="#DDCCFF"))	
		
		if not self._tag_list.has_key(self._current_doc):
			self._tag_list[self._current_doc] = {}
		
		#initialize list for highlighted tags
		if not self._highlighted_pairs.has_key(self._current_doc):
			self._highlighted_pairs[self._current_doc] = []		
		
	def start_highlighting(self):
		selection = self._current_doc.get_selection_bounds()
		was_xml = False
		if selection:
			#first of all: remove all other tags
			for triple in self._highlighted_pairs[self._current_doc]:
				self._current_doc.remove_tag(triple[0], triple[1], triple[2])

			self._highlighted_pairs[self._current_doc] = []		
			self.highlight_xml(selection[0], selection[1], 0)
			
			#now, show all tags
			self._highlighted_pairs[self._current_doc].reverse()
			
			for triple in self._highlighted_pairs[self._current_doc]:
				for remove_tag in self._tag_lib[self._current_doc]:
					self._current_doc.remove_tag(remove_tag, triple[1], triple[2])
				self._current_doc.apply_tag(triple[0], triple[1], triple[2])	
				was_xml = True
		return was_xml
				
	def highlight_xml(self, s, e, level):
		#self.alert(self._current_doc.get_text(s,e))
		is_xml = self.is_xml_tag(s,e)

		if is_xml:
			selected_text = self._current_doc.get_text(s, e)
			selected_text = self.format_starttag(selected_text)
			closing_tag_iter = self.move_to_end_tag(s.copy(), selected_text, level)

			if closing_tag_iter:
				self._highlighted_pairs[self._current_doc].append([self._tag_lib[self._current_doc][level % len(self._tag_lib[self._current_doc])], s, closing_tag_iter])

	#scan a line and count the tags
	def move_to_end_tag(self, start_iter, start_tag, level):
		end_tag = "</" + start_tag[1:] + ">"
		self._tag_list[self._current_doc][start_tag] = 0
		self._tag_list[self._current_doc][end_tag] = 0

		has_next_line = True #Is there a current line?
		is_first_line = True #Are we on the first line of the scanning process?
		self._is_inline = False #Flag for inline commands
		
		while(has_next_line):
			s = start_iter
			e = start_iter.copy()

			#not on first line? set index to beginning
			if not is_first_line:
				s.set_line_offset(0)
			is_first_line = False

			#move to end of line
			e.forward_to_line_end()

			#little hack to jump over empty lines
			if e.get_line() > s.get_line():
				s.set_line(e.get_line())
				s.set_line_offset(0)

			#scan for XML tags
			line_content = s.get_text(e)
			line_content = self._current_doc.get_text(s,e)
			scan_current_line = True
			reg_ex = "<[a-zA-Z0-9_]+"

			#iterate over all found tags
			found_tags = re.findall(reg_ex, line_content)
			another_tag = None
			for found_tag in found_tags:
				if found_tag != start_tag:
					another_tag = found_tag
					break
					
			#another tag found in line? recursively call highlight_xml again
			if another_tag: #TODO: also be aware of the same tag opening again in the same line!
				pos_another_tag = string.find(line_content, another_tag) 
				s1 = s.copy()
				e1 = s1.copy()
				s1.set_offset(s1.get_offset() + pos_another_tag)
				e1.set_offset(s1.get_offset() + len(another_tag))
				self.highlight_xml(s1, e1, level + 1)
			
			while scan_current_line:
				#special case: inline tags like <example test="blahblah"/>
				pos_closed_tag = string.find(line_content, "/>")
				#found "/>" and no other "<" in between? Then this is an inline command
				if pos_closed_tag > 0 and string.find(line_content[1:pos_closed_tag], "<") == -1 and string.find(line_content[0:pos_closed_tag], start_tag) >= 0:
					#nothing else found so far? begins with inline command. so, presume, this is the one we want to mark.
					if self._tag_list[self._current_doc][start_tag] == 0:
						s1 = s.copy() #position to conintue scanning from; also position behind "/>"
						s1.set_offset(s.get_offset() + pos_closed_tag + 2)
						#append this inline tag to the list of sections to be highlighted
						self._highlighted_pairs[self._current_doc].append([self._tag_lib[self._current_doc][level % len(self._tag_lib[self._current_doc])], s, s1])
						return s1
					else:
						#rest offset of s and continue scanning. Basically ignoring inline tags in this case...
						s.set_offset(s.get_offset() + pos_closed_tag + 2)
						line_content = self._current_doc.get_text(s,e)

				#check for start_tag: does it open up again? if so, is there a closing tag before or after?
				pos_start_tag = string.find(line_content, start_tag)
				pos_end_tag   = string.find(line_content, end_tag)

				found_start_tag = (pos_start_tag >= 0)
				found_end_tag = (pos_end_tag >= 0)

				#there is a start-tag, but no end-tag or: there is a start-tag and an endtag, but the start-tag is before end-tag
				if (found_start_tag and not found_end_tag) or (found_start_tag and found_end_tag and pos_start_tag < pos_end_tag):
					self._tag_list[self._current_doc][start_tag] = self._tag_list[self._current_doc][start_tag] + 1
					s.set_offset(s.get_offset() + pos_start_tag + len(start_tag))
					line_content = self._current_doc.get_text(s,e)
				elif (found_end_tag and not found_start_tag) or (found_start_tag and found_end_tag and pos_end_tag < pos_start_tag):
					self._tag_list[self._current_doc][end_tag] = self._tag_list[self._current_doc][end_tag] + 1
					if self._tag_list[self._current_doc][end_tag] == self._tag_list[self._current_doc][start_tag]:
						scan_current_line = False
					s.set_offset(s.get_offset() + pos_end_tag + len(end_tag))
					line_content = self._current_doc.get_text(s,e)

				else:
					scan_current_line = False

				#are there as many start- and end-tags? return the iter (which is now behind the last closed tag)
				if self._tag_list[self._current_doc][end_tag] == self._tag_list[self._current_doc][start_tag]:
					if s.get_offset() > e.get_offset():
						return e
					else:
						return s

			#move on to the next line
			has_next_line = start_iter.forward_line()
		return None		

	#format the starttag: to ignore all attributes, kick out the ">" if present
	def format_starttag(self, tag):
		if tag[-1:] == ">":
			return tag[0:-1]
		else:
			return tag
			
	#place s and e to the beginning and end of the tag
	def is_xml_tag(self, s, e):
		#complete tag selected
		selected_text = self._current_doc.get_text(s, e)
		is_xml = (selected_text.strip()[0] == "<")
		if is_xml:
			return True	

		#only tag keyword selected	
		if s.get_line_index() > 0:
			s.set_line_index(s.get_line_index() - 1)
		selected_text = self._current_doc.get_text(s, e)
		return (selected_text.strip()[0] == "<")

	#highlight single words instead of xml trees
	def highlight_selection(self):
		selection = self._current_doc.get_selection_bounds()

		if selection:
			self._current_doc.set_enable_search_highlighting(True)
			s,e = selection
			selected_text = self._current_doc.get_text(s, e)
			self._current_doc.set_search_text(selected_text, 1)		
		
			