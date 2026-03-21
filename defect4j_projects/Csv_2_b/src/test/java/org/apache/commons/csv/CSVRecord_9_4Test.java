package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.Serializable;
import java.util.Arrays;
import java.util.Iterator;

import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

import java.lang.reflect.Constructor;
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;

public class CSVRecord_9_4Test {

    private CSVRecord createCSVRecord(String[] values, Map<String, Integer> mapping, String comment, long recordNumber) throws Exception {
        Constructor<CSVRecord> constructor = CSVRecord.class.getDeclaredConstructor(String[].class, Map.class, String.class, long.class, boolean.class);
        constructor.setAccessible(true);
        return constructor.newInstance(values, mapping, comment, recordNumber, false);
    }

    @Test
    @Timeout(8000)
    public void testGetCommentReturnsComment() throws Exception {
        String[] values = new String[] {"a", "b"};
        Map<String, Integer> mapping = new HashMap<>();
        String comment = "This is a comment";
        long recordNumber = 1L;

        CSVRecord record = createCSVRecord(values, mapping, comment, recordNumber);

        assertEquals(comment, record.getComment());
    }

    @Test
    @Timeout(8000)
    public void testGetCommentReturnsNullWhenNoComment() throws Exception {
        String[] values = new String[] {"x", "y"};
        Map<String, Integer> mapping = Collections.emptyMap();
        String comment = null;
        long recordNumber = 2L;

        CSVRecord record = createCSVRecord(values, mapping, comment, recordNumber);

        assertNull(record.getComment());
    }
}